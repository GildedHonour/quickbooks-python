from quickbooks import QuickBooks
import datetime

app_token = "eb81179fbbb15b45e4baeb4b665456d40dc6"
consumer_key = "qyprd0mBqvG5ZNPkkchfbZez3eKq0K"
consumer_secret = "QuwKEiFGHEKubirxTAVkTQkKXEYmiHIEGzMJscUY"
callback_url = "https://www.somecompany.com/callback"
access_token = "qyprdXNLmLvvQEUgR1v3E7aaa3oK5LvKth42biHFv41coaan"
access_token_secret = "fa4slHamwst8lXqeGnNNr0FueuzUxFYxHE1vKBXo"
company_id = 1243290815

# a client
class C1(object):
    # a callback function, it must accept 3 arguments
    def on_refresh_token(self, added_at, access_token, access_tokne_s):
        print "on_refresh_token"
        print "added: {}, acc_t: {}, access_ts: {}".format(added_at, access_token, access_tokne_s)

c1 = C1()
qb = QuickBooks(consumer_key=consumer_key, consumer_secret=consumer_secret, access_token=access_token,  access_token_secret=access_token_secret, 
    company_id=company_id, expire_date=datetime.date(2015, 11, 21), reconnect_window_days_count=30, verbosity=10,
    acc_token_changed_callback = c1.on_refresh_token # passing the callback function to QB
)

def test1():
    print "Attachments request..."
    existing_attachables = qb.get_objects("Attachable")
    print "Existing Attachable objects length: %d" % len(existing_attachables)
    new_attachment1_id = qb.upload_file("for_upload/test1.pdf")
    updated_attachables_list = qb.get_objects("Attachable")
    print "Updated list of Attachable objects length: %d" % len(updated_attachables_list)

def test2():
    print "Reconnect request..."
    qb._reconnect() 

test1()