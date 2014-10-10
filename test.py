from quickbooks import QuickBooks

app_token = "eb81179fbbb15b45e4baeb4b665456d40dc6" # not sure what this is for
consumer_key = "qyprd0mBqvG5ZNPkkchfbZez3eKq0K"
consumer_secret = "QuwKEiFGHEKubirxTAVkTQkKXEYmiHIEGzMJscUY"
callback_url = "https://www.somecompany.com/callback"
access_token = "qyprdXNLmLvvQEUgR1v3E7aaa3oK5LvKth42biHFv41coaan"
access_token_secret = "fa4slHamwst8lXqeGnNNr0FueuzUxFYxHE1vKBXo"
company_id = 1243290815  # this is a paid company I set up for this job
attachment_dir = "for_upload" # for your convenience
qb = QuickBooks(consumer_key=consumer_key, consumer_secret=consumer_secret, 
                access_token=access_token, 
                access_token_secret=access_token_secret, 
                company_id=company_id,
                verbosity=10)

def test1():
    existing_attachables = qb.get_objects("Attachable")
    print "Existing Attachable objects length: %d" % len(existing_attachables)

    new_attachment1_path = attachment_dir+"/test1.pdf"   
    new_attachment1_id = qb.upload_file(new_attachment1_path)

    updated_attachables_list = qb.get_objects("Attachable")
    print "Updated list of Attachable objects length: %d" % len(updated_attachables_list)

def test2():
    res = qb.reconnect() 
    print res



test2()