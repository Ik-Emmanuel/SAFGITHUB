from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
import urllib
# from flask_wtf.csrf import CsrfProtect
# from urllib.parse import urlparse

# csrf = CsrfProtect()
app = Flask(__name__)
app.config.from_object(Config)
# print(Config.SECRET_KEY)
# csrf.init_app(app)
params = urllib.parse.quote_plus("Driver={ODBC Driver 17 for SQL Server};Server=tcp:businessinsight.database.windows.net,1433;Database=FraudSolutionDBExt;Uid=edouser;Pwd=data18@@$$;Encrypt=yes;TrustServerCertificate=yes;Connection Timeout=50;")

# db = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

app.config['SQLALCHEMY_DATABASE_URI'] = f"mssql+pyodbc:///?odbc_connect={params}"

db = SQLAlchemy(app)
SQLALCHEMY_TRACK_MODIFICATIONS = False
db.init_app(app)


from application import routes


if __name__ == "__main__":
    app.run(debug=True)


