from rauth import OAuth1Session, OAuth1Service
import xml.etree.ElementTree as ET
import xmltodict
from xml.dom import minidom
import requests, urllib
import json, time
import textwrap
import datetime

class QuickBooks():
    """
    A wrapper class around Python's Rauth module for Quickbooks the API
    """

    base_url_v3 =  "https://quickbooks.api.intuit.com/v3"
    base_url_v2 = "https://qbo.intuit.com/qbo1"
    request_token_url = "https://oauth.intuit.com/oauth/v1/get_request_token"
    access_token_url = "https://oauth.intuit.com/oauth/v1/get_access_token"
    authorize_url = "https://appcenter.intuit.com/Connect/Begin"
    _attemps_count = 5
    _namespace = "http://platform.intuit.com/api/v1"

    def __init__(self, **args):
        if "cred_path" in args:
            self.read_creds_from_file(args["cred_path"])

        self.session = None
        self.qb_service = None

        self.consumer_key = args.get("consumer_key", "")
        self.consumer_secret = args.get("consumer_secret", "")
        self.callback_url = args.get("callback_url", "")

        self.access_token = args.get("access_token", "")
        self.access_token_secret = args.get("access_token_secret", "")

        self.request_token = args.get("request_token", "")
        self.request_token_secret = args.get("request_token_secret", "")

        self.expire_date = args.get("expire_date", "")
        self.reconnect_window_days_count = args.get("reconnect_window_days_count", "")
        self.acc_token_changed_callback = args.get("acc_token_changed_callback", None)

        self.company_id = args.get("company_id", 0)
        self.verbosity = args.get("verbosity", 0)

        self._business_objects = ["Account","Attachable","Bill","BillPayment", "Class","CompanyInfo","CreditMemo","Customer",
            "Department","Employee","Estimate","Invoice", "Item","JournalEntry","Payment","PaymentMethod", "Preferences",
            "Purchase","PurchaseOrder", "SalesReceipt","TaxCode","TaxRate","Term", "TimeActivity","Vendor","VendorCredit"
        ]

        self._name_list_objects = ["Account", "Class", "Customer", "Department", "Employee", "Item", "PaymentMethod", "TaxCode", 
            "TaxRate", "Term", "Vendor"
        ]

        self._transaction_objects = ["Bill", "BillPayment", "CreditMemo", "Estimate", "Invoice", "JournalEntry", "Payment", "Purchase", 
            "PurchaseOrder", "SalesReceipt", "TimeActivity", "VendorCredit"
        ]

    def _reconnect_by_demand(self):
        current_date = datetime.date.today()
        days_diff = (self.expire_date - current_date).days
        if days_diff > 0:
            if days_diff <= self.reconnect_window_days_count:
                print "Going to reconnect..."
                if self._reconnect():
                    print "Reconnected successfully"
                else:    
                    print "Unable to reconnect, try again later, you have {} days left to do that".format(days_diff - self.reconnect_window_days_count)
        else:
            raise "The token is expired, unable to reconnect, please get a new one."

    def _reconnect(self, i=1):
        if i > self._attemps_count:
            print "Unable to reconnect, there're no attempts left ({} attempts sent).".format(i)
            return False
        else:
            self._create_session_by_demand()
            resp = self.session.request("GET", "https://appcenter.intuit.com/api/v1/connection/reconnect", True, self.company_id, verify=False)
            dom = minidom.parseString(ET.tostring(ET.fromstring(resp.content), "utf-8"))
            if resp.status_code == 200:
                error_code = int(dom.getElementsByTagNameNS(self._namespace, "ErrorCode")[0].firstChild.nodeValue)
                if error_code == 0:
                    print "Reconnected successfully"

                    date_raw  = dom.getElementsByTagNameNS(self._namespace, "ServerTime")[0].firstChild.nodeValue
                    from dateutil import parser
                    self.added_at = parser.parse(date_raw).date()
                    
                    self.access_token = str(dom.getElementsByTagNameNS(self._namespace, "OAuthToken")[0].firstChild.nodeValue)
                    self.access_token_secret = str(dom.getElementsByTagNameNS(self._namespace, "OAuthTokenSecret")[0].firstChild.nodeValue)
                    if self.acc_token_changed_callback:
                        self.acc_token_changed_callback(self.added_at, self.access_token, self.access_token_secret)

                    return True
                else:
                    msg = str(dom.getElementsByTagNameNS(self._namespace, "ErrorMessage")[0].firstChild.nodeValue)
                    print "An error occurred while trying to reconnect, code: {}, message: \"{}\"".format(error_code, msg)
                    i += 1
                    print "Trying to reconnect again... attempt #{}".format(i)
                    self._reconnect(i)
            else:
                print "An HTTP error {} occurred, trying again, attempt #{}".format(resp.status_code, i)
                i += 1
                self._reconnect(i)

    def _create_session_by_demand(self):
        if self.session is None:
            self.create_session()

    def get_authorize_url(self):
        """
        Returns the Authorize URL as returned by QB, and specified by OAuth 1.0a. :return URI:
        """
        self.qb_service = OAuth1Service(name=None, consumer_key=self.consumer_key, consumer_secret=self.consumer_secret,
            request_token_url=self.request_token_url, access_token_url=self.access_token_url, authorize_url=self.authorize_url,
            base_url=None
        )

        rt, rts = self.qb_service.get_request_token(params={"oauth_callback":self.callback_url})
        self.request_token, self.request_token_secret = [rt, rts]
        return self.qb_service.get_authorize_url(self.request_token)

    def get_access_tokens(self, oauth_verifier):
        """
        Wrapper around get_auth_session, returns session, and sets
        access_token and access_token_secret on the QB Object.
        :param oauth_verifier: the oauth_verifier as specified by OAuth 1.0a
        """
        session = self.qb_service.get_auth_session(self.request_token, self.request_token_secret, data={"oauth_verifier": oauth_verifier})

        self.access_token = session.access_token
        self.access_token_secret = session.access_token_secret
        return session

    def create_session(self):
        if self.consumer_secret and self.consumer_key and self.access_token_secret and self.access_token:
            self.session = OAuth1Session(self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret)
        else:
            # shouldn"t there be a workflow somewhere to GET the auth tokens?
            # add that or ask someone on oDesk to build it...
            raise Exception("Need four creds for Quickbooks.create_session.")

        return self.session

    def query_fetch_more(self, r_type, header_auth, realm, qb_object, original_payload=""):
        """ Wrapper script around keep_trying to fetch more results if there are more. 
        """
        # The maximum number of results returned by QB
        max_results = 500 
        start_position = 0
        more = True
        data_set = []
        url = "{}/company/{}/query".format(self.base_url_v3, self.company_id)

        # Edit the payload to return more results.
        payload = original_payload + " MAXRESULTS " + str(max_results)
        while more:
            r_dict = self.keep_trying(r_type, url, True, self.company_id, payload)
            try:
                access = r_dict["QueryResponse"][qb_object]
            except:
                if "QueryResponse" in r_dict and r_dict["QueryResponse"] == {}:
                    return []
                else:
                    print "FAILED", r_dict
                    r_dict = self.keep_trying(r_type, url, True, self.company_id, payload)

            # For some reason the totalCount isn"t returned for some queries,
            # in that case, check the length, even though that actually requires
            # measuring
            try:
                result_count = int(r_dict["QueryResponse"]["totalCount"])
                if result_count < max_results:
                    more = False
            except KeyError:
                try:
                    result_count = len(r_dict["QueryResponse"][qb_object])
                    if result_count < max_results:
                        more = False
                except KeyError:
                    print "\n\n ERROR", r_dict
                    pass


            if self.verbosity > 0:
                print "(batch begins with record {})".format(start_position)


            # Just some math to prepare for the next iteration
            if start_position == 0:
                start_position = 1

            start_position = start_position + max_results
            payload = "{} STARTPOSITION {} MAXRESULTS {}".format(original_payload, start_position, max_results)
            data_set += r_dict["QueryResponse"][qb_object]

        return data_set

    def create_object(self, qbbo, request_body, content_type = "json"):
        """
        One of the four glorious CRUD functions.
        Getting this right means using the correct object template and
        and formulating a valid request_body. This doesn"t help with that.
        It just submits the request and adds the newly-created object to the
        session"s brain.
        """

        if qbbo not in self._business_objects:
            raise Exception("%s is not a valid QBO Business Object." % qbbo, " (Note that this validation is case sensitive.)")

        url = "https://qb.sbfinance.intuit.com/v3/company/%s/%s" % (self.company_id, qbbo.lower())

        if self.verbosity > 0:
            print "About to create a(n) %s object with this request_body:" % qbbo
            print request_body

        response = self.hammer_it("POST", url, request_body, content_type)
        if qbbo in response:
            new_object = response[qbbo]
        else:
            return None

        new_Id = new_object["Id"]
        attr_name = qbbo+"s"
        if not hasattr(self,attr_name):
            if self.verbosity > 0:
                print "Creating a %ss attribute for this session." % qbbo

            self.get_objects(qbbo).update({new_Id:new_object})
        else:
            if self.verbosity > 8:
                print "Adding this new %s to the existing set of them." % qbbo
                print json.dumps(new_object, indent=4)

            getattr(self, attr_name)[new_Id] = new_object

        return new_object

    def read_object(self, qbbo, object_id, content_type = "json"):
        """Makes things easier for an update because you just do a read,
        tweak the things you want to change, and send that as the update
        request body (instead of having to create one from scratch)."""

        url = "https://quickbooks.api.intuit.com/v3/company/%s/%s/%s" % (self.company_id, qbbo.lower(), object_id)
        response = self.hammer_it("GET", url, None, content_type)
        if not qbbo in response:
            return response

        #otherwise we don"t need the time (and outer shell)
        return response[qbbo]

    def update_object(self, qbbo, Id, update_dict, content_type="json"):
        """
        Generally before calling this, you want to call the read_object
        command on what you want to update. The alternative is forming a valid
        update request_body from scratch, which doesn"t look like fun to me.
        """

        #todo - refactor
        if qbbo not in self._business_objects:
            raise Exception("%s is not a valid QBO Business Object." % qbbo, " (Note that this validation is case sensitive.)")

        """
        url = "https://qb.sbfinance.intuit.com/v3/company/%s/%s" % (self.company_id, qbbo.lower()) + "?operation=update"
        url = "https://quickbooks.api.intuit.com/v3/company/%s/%s" % (self.company_id, qbbo.lower()) + "?requestid=%s" % Id
        """

        #see this link for url troubleshooting info:
        #http://stackoverflow.com/questions/23333300/whats-the-correct-uri-
        # for-qbo-v3-api-update-operation/23340464#23340464

        url = "https://quickbooks.api.intuit.com/v3/company/%s/%s" % (self.company_id, qbbo.lower())

        # NO! DON'T DO THAT, THEN YOU CAN'T DELETE STUFF YOU WANT TO DELETE!
        e_dict = update_dict
        request_body = json.dumps(e_dict, indent=4)
        if self.verbosity > 0:
            print "About to update %s Id %s with this request_body:" % (qbbo, Id)
            print request_body
            if self.verbosity > 9:
                raw_input("Waiting...")

        response = self.hammer_it("POST", url, request_body, content_type)
        if qbbo in response:
            new_object = response[qbbo]
        else:
            return None

        attr_name = qbbo+"s"
        if not hasattr(self,attr_name):
            if self.verbosity > 0:
                print "Creating a %ss attribute for this session." % qbbo

            self.get_objects(attr_name).update({new_Id:new_object})

        else:
            if self.verbosity > 8:
                print "Adding this new %s to the existing set of them." % qbbo
                print json.dumps(new_object, indent=4)

            getattr(self, attr_name)[Id] = new_object

        return new_object

    def delete_object(self, qbbo, object_id=None, content_type="json", json_dict=None):
        """
        Don"t need to give it an Id, just the whole object as returned by
        a read operation.
        """

        if not json_dict:
            if object_id:
                json_dict = self.read_object(qbbo, object_id)
            else:
                raise Exception("Need either an Id or an existing object dict!")

        if not "Id" in json_dict: #todo - rename "Id"
            print json.dumps(json_dict, indent=4)
            raise Exception("No Id attribute found in the above dict!")

        request_body = json.dumps(json_dict, indent=4)
        url = "https://quickbooks.api.intuit.com/v3/company/%s/%s" % (self.company_id, qbbo.lower())
        response = self.hammer_it("POST", url, request_body, content_type, **{"params":{"operation":"delete"}})
        if not qbbo in response:
            return response

        return response[qbbo]

    def upload_file(self, path, qbbo=None, Id=None): #todo - refactor
        """
        Uploads a file that can be linked to a specific transaction (or other entity probably), or not.
        Either way, it should return the id the attachment.
        """

        url = "https://quickbooks.api.intuit.com/v3/company/%s/upload" % self.company_id
        bare_name, extension = path.rsplit("/",1)[-1].rsplit(".",1)
        result = self.hammer_it("POST", url, None, "multipart/formdata", file_name=path)
        attachment_id = result["AttachableResponse"][0]["Attachable"]["Id"]
        return attachment_id

    #todo - refactor
    def download_file(self, attachment_id, destination_dir="", alternate_name=None):
        """
        Download a file to the requested (or default) directory, then also
        return a download link for convenience.
        """
        url = "https://quickbooks.api.intuit.com/v3/company/%s/download/%s" % (self.company_id, attachment_id)
        link =  self.hammer_it("GET", url, None, "json", accept="filelink")
        success = False
        tries_remaining = 6
        while not success and tries_remaining >= 0:
            if self.verbosity > 0 and tries_remaining < 6:
                print "This is attempt #%d to download Attachable id %s." % (6-tries_remaining+1, attachment_id)

            try:
                my_r = requests.get(link)
                if alternate_name:
                    filename = alternate_name
                else:
                    filename = urllib.unquote(my_r.url)
                    filename = filename.split("/./")[1].split("?")[0]

                with open(destination_dir + filename, "wb") as f:
                    for chunk in my_r.iter_content(1024):
                        f.write(chunk)

                success = True
            except:
                tries_remaining -= 1
                time.sleep(1)
                if tries_remaining == 0:
                    print "Max retries reached..."
                    raise #todo
                                   
        return link

    def hammer_it(self, request_type, url, request_body, content_type, accept="xml", file_name=None, **req_kwargs):
        """
        A slim version of simonv3"s excellent keep_trying method. Among other
         trimmings, it assumes we can only use v3 of the
         QBO API. It also allows for requests and responses
         in xml OR json. (No xml parsing added yet but the way is paved...)
        """
        self._create_session_by_demand()
        trying = True #todo 
        print_error = False
        tries = 0 
        while trying:
            tries += 1
            if tries > 1:
                #we don"t want to get shut out...
                time.sleep(1)

            if self.verbosity > 0 and tries > 1:
                print "(this is try#%d)" % tries

            if accept == "filelink":
                headers = {}
            else:
                headers = {"Accept": "application/%s" % accept}

            if file_name == None:
                if not request_type == "GET":
                    headers.update({"Content-Type":  "application/%s" % content_type})
            else:
                boundary = "-------------PythonMultipartPost"
                headers.update({"Content-Type": "multipart/form-data; boundary={}".format(boundary),
                    "Accept-Encoding": "gzip;q=1.0,deflate;q=0.6,identity;q=0.3", "User-Agent": "OAuth gem v0.4.7",
                    "Accept":"application/json", "Connection": "close"
                })

                with open(file_name, "rb") as file_handler:
                    binary_data = file_handler.read()

                request_body = textwrap.dedent(
                    """
                    --{}
                    Content-Disposition: form-data; name="file_content_0"; filename="{}"
                    Content-Length: {}
                    Content-Type: image/jpeg
                    Content-Transfer-Encoding: binary

                    {}

                    --{}--
                    """
                ).format(boundary, file_name, len(binary_data), binary_data, boundary)


            self._reconnect_by_demand()
            resp = self.session.request(request_type, url, True, self.company_id, headers=headers, data=request_body, verify=False, **req_kwargs)
            resp_cont_type = resp.headers["content-type"]
            if "xml" in resp_cont_type:
                result = ET.fromstring(resp.content)
                rough_string = ET.tostring(result, "utf-8")
                reparsed = minidom.parseString(rough_string)
                if self.verbosity > 0:
                    print resp
                    if resp.status_code == 503:
                        print " (Service Unavailable)"
                    elif resp.status_code == 401:
                        print " (Unauthorized -- a dubious response)"
                    else:
                        print " (json parse failed)"

                if self.verbosity > 8:
                    print resp.text
                    result = None

            elif "json" in resp_cont_type:
                try:
                    result = my_r.json()
                except:
                    result = {"Fault" : {"type":"(inconclusive)"}}

                if "Fault" in result and "type" in result["Fault"] and result["Fault"]["type"] == "ValidationFault":
                    trying = False
                    print_error = True

                elif tries >= 10:
                    trying = False
                    if "Fault" in result:
                        print_error = True

                elif "Fault" not in result:
                    #sounds like a success
                    trying = False

                if (not trying and print_error):
                    print json.dumps(result, indent=1)

            elif "plain/text" in resp_cont_type or accept == "filelink":
                if not "Fault" in resp.text or tries >= 10:
                    trying = False

                else:
                    print "Failed to get file link."
                    if self.verbosity > 4:
                        print resp.text

                result = resp.text

            elif "text/html" in resp_cont_type:
                pass #todo -???
            else:
                raise NotImplementedError("How do I parse a %s response?" % resp_cont_type) #todo

        return result

    def keep_trying(self, r_type, url, header_auth, realm, payload=""):
        """ 
        Wrapper script to session.request() to continue trying at the QB
        API until it returns something good, because the QB API is
        inconsistent 
        """
        
        self._create_session_by_demand()

        trying = True
        tries = 0
        while trying:
            tries += 1
            if tries > 1:
                if self.verbosity > 0:
                    pass
                time.sleep(1)

            if self.verbosity > 0 and tries > 1:
                print "(this is try#%d)" % tries

            if "v2" in url:
                r = self.session.request(r_type, url, header_auth, realm, data=payload)
                r_dict = xmltodict.parse(r.text)
                if "FaultInfo" not in r_dict or tries > 10:
                    trying = False
            else:
                headers = {"Content-Type": "application/text", "Accept": "application/json"}
                r = self.session.request(r_type, url, header_auth, realm, headers=headers, data=payload, verify=False)
                try:
                    r_dict = r.json()
                except:
                    #I've seen, e.g. a ValueError ("No JSON object could be decoded"), but there could be other errors here...
                    if self.verbosity > 0:
                        pass
                    r_dict = {"Fault":{"type":"(Inconclusive)"}}

                if "Fault" not in r_dict or tries > 10:
                    trying = False
                elif "Fault" in r_dict and r_dict["Fault"]["type"] == "AUTHENTICATION":
                    #Initially I thought to quit here, but actually
                    #it appears that there are "false" authentication
                    #errors all the time and you just have to keep trying...

                    if tries > 15: #todo
                        trying = False
                    else:
                        trying = True

        if "Fault" in r_dict:
            print r_dict

        return r_dict

    def fetch_customer(self, pk):
        if pk:
            url = self.base_url_v3 + "/company/%s/customer/%s" % (self.company_id, pk)
            r_dict = self.keep_trying("GET", url, True, self.company_id)
            return r_dict["Customer"]

    def fetch_customers(self, all=False, page_num=0, limit=10):
        self._create_session_by_demand()
        url = "{}/resource/customers/v2/{}".format(self.base_url_v2, self.company_id)
        customers = []
        if all:
            counter = 1
            more = True
            while more:
                payload = {"ResultsPerPage":30, "PageNum":counter}
                trying = True
                while trying:
                    r = self.session.request("POST", url, header_auth=True, data=payload, realm=self.company_id)
                    root = ET.fromstring(r.text)
                    if root[1].tag != "{http://www.intuit.com/sb/cdm/baseexceptionmodel/xsd}ErrorCode":
                        trying = False
                    else:
                        print "Failed"

                self.session.close() #todo - needed?
                qb_name = "{http://www.intuit.com/sb/cdm/v2}"
                for child in root:
                    if child.tag == "{http://www.intuit.com/sb/cdm/qbo}Count":
                        if int(child.text) < 30:
                            more = False
                            print "Found all customers"

                    if child.tag == "{http://www.intuit.com/sb/cdm/qbo}CdmCollections":
                        for customer in child:
                            customers += [xmltodict.parse(ET.tostring(customer))]

                counter += 1
        else:
            payload = {"ResultsPerPage":str(limit), "PageNum":str(page_num)}
            r = self.session.request("POST", url, header_auth=True, data=payload, realm=self.company_id)
            root = ET.fromstring(r.text)

            #TODO: parse for all customers

        return customers

    def fetch_sales_term(self, pk):
        if pk:
            url = self.base_url_v2 + "/resource/sales-term/v2/%s/%s" % ( self.company_id, pk)

            r_dict = self.keep_trying("GET", url, True, self.company_id)
            return r_dict

    def fetch_invoices(self, **args):
        qb_object = "Invoice"
        payload = "SELECT * FROM %s" % (qb_object)
        if "query" in args:
            if "customer" in args["query"]:
                payload = ("SELECT * FROM %s WHERE CustomerRef = '%s'") % (qb_object, args["query"]["customer"])

        r_dict = self.query_fetch_more("POST", True, self.company_id, qb_object, payload)
        return r_dict


    def fetch_purchases(self, **args):
        qb_object = "Purchase"
        payload = ""
        if "query" in args and "customer" in args["query"]:

            # if there is a customer, let"s get the create date
            # for that customer in QB, all relevant purchases will be
            # after that date, this way we need less from QB

            #todo - refactor
            customer = self.fetch_customer(args["query"]["customer"])
            payload = "SELECT * FROM {} WHERE MetaData.CreateTime > '{}'".format(qb_object, customer["MetaData"]["CreateTime"])

        else:
            payload = "SELECT * FROM {}".format(qb_object)

        unfiltered_purchases = self.query_fetch_more("POST", True, self.company_id, qb_object, payload)
        filtered_purchases = []

        #todo - refactor
        if "query" in args and "customer" in args["query"]:
            for entry in unfiltered_purchases:
                if ("Line" in entry):
                    for line in entry["Line"]:
                        if ("AccountBasedExpenseLineDetail" in line and "CustomerRef" in \
                                line["AccountBasedExpenseLineDetail"] and \
                                line["AccountBasedExpenseLineDetail"]["CustomerRef"]["value"] == args["query"]["customer"]
                            ):

                            filtered_purchases += [entry]

            return filtered_purchases

        else:
            return unfiltered_purchases

    def fetch_journal_entries(self, **args):
        """ Because of the beautiful way that journal entries are organized
        with QB, you"re still going to have to filter these results for the
        actual entity you"re interested in.

        :param query: a dictionary that includes "customer",
        and the QB id of the customer
        """

        payload = {}
        more = True
        journal_entries = []
        max_results = 500
        start_position = 0

        if "query" in args and "project" in args["query"]:
            original_payload = "SELECT * FROM JournalEntry"
        elif "query" in args and "raw" in args["query"]:
            original_payload = args["query"]["raw"]
        else:
            original_payload = "SELECT * FROM JournalEntry"

        payload = original_payload + " MAXRESULTS " + str(max_results)
        while more:
            url = "{}/company/{}/query".format(self.base_url_v3, self.company_id)
            r_dict = self.keep_trying("POST", url, True, self.company_id, payload)
            if int(r_dict["QueryResponse"]["totalCount"]) < max_results:
                more = False
            if start_position == 0:
                start_position = 1
            start_position = start_position + max_results
            payload = "%s STARTPOSITION %s MAXRESULTS %s" % (original_payload, start_position, max_results)
            journal_entry_set = r_dict["QueryResponse"]["JournalEntry"]

            # This has to happen because the QBO API doesn"t support
            # filtering along customers apparently.
            # todo - refactor
            if "query" in args and "class" in args["query"]:
                for entry in journal_entry_set:
                    for line in entry["Line"]:
                        if "JournalEntryLineDetail" in line:
                            if "ClassRef" in line["JournalEntryLineDetail"]:
                                if args["query"]["class"] in line["JournalEntryLineDetail"]["ClassRef"]["name"]:
                                    journal_entries += [entry]
                                    break

            else:
                journal_entries = journal_entry_set

        return journal_entries

    def fetch_bills(self, **args):
        """
        Fetch the bills relevant to this project.
        """
        payload = {}
        more = True
        counter = 1
        bills = []
        max_results = 500
        start_position = 0
        if "query" in args and "customer" in args["query"]:
            original_payload = "SELECT * FROM Bill"
        elif "query" in args and "raw" in args["query"]:
            original_payload = args["query"]["raw"]
        else:
            original_payload = "SELECT * FROM Bill"

        payload = original_payload + " MAXRESULTS " + str(max_results)
        while more:
            url = self.base_url_v3 + "/company/%s/query" % (self.company_id)
            r_dict = self.keep_trying("POST", url, True, self.company_id, payload)
            counter += 1
            if int(r_dict["QueryResponse"]["maxResults"]) < max_results:
                more = False

            #take into account the initial start position
            #todo
            if start_position == 0:
                start_position = 1
            
            start_position = start_position + max_results

            # set new payload
            payload = "{} STARTPOSITION {} MAXRESULTS {}".format(original_payload, start_position, max_results)
            bill = r_dict["QueryResponse"]["Bill"]

            # This has to happen because the QBO API doesn"t support
            # filtering along customers apparently.
            if "query" in args and "class" in args["query"]:
                for entry in bill:
                    for line in entry["Line"]:
                        if "AccountBasedExpenseLineDetail" in line:
                            line_detail = line["AccountBasedExpenseLineDetail"]
                            if "ClassRef" in line_detail:
                                name = line_detail["ClassRef"]["name"]
                                if args["query"]["class"] in name:
                                    bills += [entry]
                                    break
            else:
                bills += bill

        return bills

    def get_report(self, report_name, params = {}):
        """
        Tries to use the QBO reporting API:
        https://developer.intuit.com/docs/0025_quickbooksapi/0050_data_services/reports
        """

        url = "https://quickbooks.api.intuit.com/v3/company/%s/" % self.company_id + "reports/%s" % report_name
        added_params_count = 0
        return self.hammer_it("GET", url, None, "json", **{"params" : params})

    def query_objects(self, business_object, params={}, query_tail = ""):
        """
        Runs a query-type request against the QBOv3 API
        Gives you the option to create an AND-joined query by parameter
            or just pass in a whole query tail
        The parameter dicts should be keyed by parameter name and
            have twp-item tuples for values, which are operator and criterion
        """

        if business_object not in self._business_objects:
            raise Exception("{} not in list of QBO Business Objects. Please use one of the following: {}").format(
                business_object, self._business_objects
            )

        #eventually, we should be able to select more than just *,
        #but chances are any further filtering is easier done with Python
        #than in the query...

        query_string = "SELECT * FROM " + business_object
        if query_tail == "" and not params == {}:

            #It"s not entirely obvious what are valid properties for
            #filtering, so we"ll collect the working ones here and
            #validate the properties before sending it
            #datatypes are defined here:
            #https://developer.intuit.com/docs/0025_quickbooksapi/0050_data_services/020_key_concepts/0700_other_topics

            props = {"TxnDate": "Date", "MetaData.CreateTime": "DateTime", "MetaData.LastUpdatedTime": "DateTime"}
            p = params.keys()

            #only validating the property name for now, not the DataType
            if p[0] not in props:
                raise Exception("Unfamiliar property: {}".format(p[0]))

            query_string += " WHERE {} {} {}".format(p[0], params[p[0]][0], params[p[0]][1])
            if len(p) > 1:
                for i in range(1,len(p)+1):
                    if p[i] not in props:
                        raise Exception("Unfamiliar property: {}".format(p[i]))

                    query_string += " AND {} {} {}".format(p[i], params[p[i]][0], params[p[i]][1])

        elif not query_tail == "":
            if not query_tail[0]==" ":
                query_tail = " " + query_tail
            query_string += query_tail

        url = "{}/company/{}/query".format(self.base_url_v3, self.company_id)
        results = self.query_fetch_more(r_type="POST", header_auth=True, realm=self.company_id, qb_object=business_object,
            original_payload=query_string
        )

        return results

    def get_objects(self, qbbo, requery=False, params={}, query_tail=""):
        """
        Rather than have to look up the account that"s associate with an
        invoice item, for example, which requires another query, it might
        be easier to just have a local dict for reference.

        The same is true with linked transactions, so transactions can
        also be cloned with this method
        """

        #we"ll call the attributes by the Business Object"s name + "s",
        #case-sensitive to what Intuit"s documentation uses

        if qbbo not in self._business_objects:
            raise Exception("{} is not a valid QBO Business Object.".format(qbbo))

        elif qbbo in self._name_list_objects and query_tail == "":
            #to avoid confusion from "deleted" accounts later...
            query_tail = "WHERE Active IN (true,false)"

        attr_name = qbbo + "s"

        #if we"ve already populated this list, only redo if told to
        #because, say, we"ve created another Account or Item or something
        #during the session
        if not hasattr(self,attr_name) or requery:
            if self.verbosity > 0:
                print "Caching list of %ss." % qbbo

            object_list = self.query_objects(qbbo, params, query_tail)

            #let"s dictionarize it (keyed by Id), though, for easy lookup later
            object_dict = {}
            for o in object_list:
                Id = o["Id"]
                object_dict[Id] = o

            setattr(self, attr_name, object_dict)

        return getattr(self,attr_name)

    def object_dicts(self, qbbo_list=[], requery=False, params={}, query_tail=""):
        """
        returns a dict of dicts of ALL the Business Objects of
        each of these types (filtering with params and query_tail)
        """

        object_dicts = {}
        for qbbo in qbbo_list:
            if qbbo == "TimeActivity":
                #for whatever reason, this failed with some basic criteria, so
                query_tail = ""
            elif qbbo in self._name_list_objects and query_tail == "":
                #just something to avoid confusion from "deleted" accounts later
                query_tail = "WHERE Active IN (true,false)"

            object_dicts[qbbo] = self.get_objects(qbbo, requery, params, query_tail)

        return object_dicts

    def names(self, requery=False, params={}, query_tail="WHERE Active IN (true,false)"):
        """
        Get a dict of every Name List Business Object (of every type)
        results are subject to the filter if applicable
        returned dict has two dimensions:
        name = names[qbbo][Id]
        """

        return self.object_dicts(self._name_list_objects, requery, params, query_tail)

    def transactions(self, requery=False, params={}, query_tail=""):
        """
        Get a dict of every Transaction Business Object (of every type)
        results are subject to the filter if applicable
        returned dict has two dimensions:
        transaction = transactions[qbbo][Id]
        """

        return self.object_dicts(self._transaction_objects, requery, params, query_tail)