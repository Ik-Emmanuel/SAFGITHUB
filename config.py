import os 


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or "secret_keyS"


    # MONGODB_SETTINGS = { 'db' : 'DOC_Int'}