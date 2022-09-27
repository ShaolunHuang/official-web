from crypt import methods
from datetime import datetime, timedelta, time
from fileinput import filename
import imp
from sqlite3 import Timestamp
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session
import pyodbc
import logging
import random
import redis
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.trace.samplers import ProbabilitySampler


import os, uuid
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, __version__
from azure.servicebus import ServiceBusClient, ServiceBusMessage


app = Flask(__name__)
app.secret_key = 'super secret key'
app.permanent_session_lifetime = timedelta(minutes=5)


logger = logging.getLogger(__name__)

logger.addHandler(AzureLogHandler(
    connection_string='InstrumentationKey=c8aafd8d-09d3-4662-a448-e9c4ca7767b1')
)

middleware = FlaskMiddleware(
    app,
    exporter=AzureExporter(connection_string="InstrumentationKey=c8aafd8d-09d3-4662-a448-e9c4ca7767b1"),
    sampler=ProbabilitySampler(rate=1.0),
)

config = {
        "log_level": "DEBUG",
        "logging_enabled": "true",
        "app_insights_key": "c8aafd8d-09d3-4662-a448-e9c4ca7767b1",
}



def send_single_message(sender,msg):
    # create a Service Bus message
    message = ServiceBusMessage(msg)
    # send the message to the queue
    sender.send_messages(message)
    print("Sent a single message")
    logger.warning('Sent a single message')

@app.route('/')
def homepage():
    logger.warning('Homepage requested')
    return render_template('homepage.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/index',methods=['POST','GET'])
def index():
    userName=""
    email=""
    logger.warning('Index requested')
    server = 'mysqlforweb-123.database.windows.net'
    database = 'dbforweb'
    username = 'azureuser'
    password = '{Hsl@020716}'   
    driver= '{ODBC Driver 17 for SQL Server}'
    try:
        with pyodbc.connect('DRIVER='+driver+';SERVER=tcp:'+server+';PORT=1433;DATABASE='+database+';UID='+username+';PWD='+ password) as conn:
            with conn.cursor() as cursor:
                logger.warning('DB connection established')
                if request.method == 'POST':
                    if request.form['action'] == "Register":
                        userName = request.form.get('userName')
                        email = request.form.get('email')
                        password = request.form.get('password')
                        confirmPassword = request.form.get('confirmPassword')
                        captcha = request.form.get('captcha')
                        cursor.execute("SELECT * FROM dbo.UserInfo WHERE UserName = '" + userName + "'")
                        row = cursor.fetchone()
                        redisHost = "alanweb.redis.cache.windows.net"
                        redisPass = "FAl24qokddXZ11UUoMVpCD7fwsOUtLw1IAzCaFFB76s="
                        r = redis.StrictRedis(host=redisHost,port=6380,password=redisPass,ssl=True)
                        print(str(r.ping()))
                        if not (userName and email and password and confirmPassword and captcha):
                            flash("Please fill in every field!")
                            return redirect(url_for('index'))
                        elif password != confirmPassword:
                            flash("Passwords do not match!")
                            return redirect(url_for('index'))
                        elif row:
                            flash("User already exists!")
                        elif r.get(userName).decode("utf-8") != captcha:
                            print(r.get(userName).decode("utf-8"))
                            flash("Captcha is incorrect or expired!")
                            return redirect(url_for('index'))
                        else:
                            cursor.execute("INSERT INTO dbo.UserInfo (UserName, Email, Password, Portrait) VALUES( '"+ userName + "', '" + email + "', CONVERT(VARCHAR(256),HASHBYTES('SHA2_256', '" + password + "'),2),0)")
                            r.delete(userName)
                            flash("Registration successful!")
                            return redirect(url_for('index'))
                    elif request.form['action'] == "Login":
                        session.permanent = True
                        userName = request.form.get('userName')
                        password = request.form.get('password')
                        if not (userName and password):
                            flash("Please fill in every field!")
                            return redirect(url_for('index'))
                        else:
                            cursor.execute("SELECT * FROM [dbo].[UserInfo] WHERE UserName = '" + userName + "' AND Password = CONVERT(VARCHAR(256),HASHBYTES('SHA2_256', '" + password + "'),2)")
                            row = cursor.fetchone()
                            if row:
                                cursor.execute("SELECT * FROM dbo.UserInfo WHERE UserName = '" + userName + "' AND Portrait = 0")
                                row2 = cursor.fetchone()
                                session["userName"] = userName
                                if row2:
                                    session["portrait"] = 0
                                else:
                                    session["portrait"] = 1
                                print(session["portrait"])
                                return redirect(url_for('mainpage'))
                            else:
                                flash("Invalid username or password!")
                                return redirect(url_for('index'))
                    elif request.form['action'] == "GetCaptcha":
                        userName = request.form.get('userName')
                        email = request.form.get('email')
                        if not (userName and email):
                            flash("Please fill in every field!")
                            return redirect(url_for('index'))
                        captcha = random.randint(100000,999999)
                        redisHost = "alanweb.redis.cache.windows.net"
                        redisPass = "FAl24qokddXZ11UUoMVpCD7fwsOUtLw1IAzCaFFB76s="
                        r = redis.StrictRedis(host=redisHost,port=6380,password=redisPass,ssl=True)
                        print(str(r.ping()))
                        if r.get(userName):
                            flash("Please wait for a while!")
                            return redirect(url_for('index'))
                        r.set(name=userName,value=str(captcha),ex=600)
                        servicebus_client = ServiceBusClient.from_connection_string(conn_str="Endpoint=sb://servicebusforalanweb.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=8bLPvZsK3fraRmKQWcyvIJlfqb4x3VZBUpI0d1ZN0nY=", logging_enable=True)
                        with servicebus_client:
                            # get a Queue Sender object to send messages to the queue
                            sender = servicebus_client.get_queue_sender(queue_name="alanwebqueue")
                            with sender:
                                send_single_message(sender,email+","+str(captcha))
                                flash("Captcha sent to your email!")
                        return render_template('index.html',userName=userName,email=email)
                    else: 
                        print("Invalid action!")
                        logger.exception('fatal error, unknown action')
                else:
                    if "userName" in session:
                        flash("You are already logged in!")
                        return redirect(url_for('mainpage'))
    except Exception as e:
        print(e)
        logger.exception('fatal error, cannot connect to DB')
    return render_template('index.html')


@app.route('/mainpage',methods=['POST','GET'])
def mainpage():
    logger.warning('Mainpage requested')
    if request.method == 'POST':
        if request.form['action'] == "Logout":
            session.pop('userName', None)
            session.pop('portrait', None)
            flash("Logout successful!")
            return redirect(url_for('homepage'))
        elif request.form['action'] == "Upload":
            file = request.files['file']
            fileName = file.filename
            if fileName == '' or fileName.split('.')[-1] not in ['jpg', 'png','jpeg','gif','JPG','PNG','JPEG','GIF']:
                flash("Invalid file! Please upload a valid image file in 10 MB!")
                return redirect(url_for('mainpage'))
            else:
                try:
                    connect_str = "DefaultEndpointsProtocol=https;AccountName=storagealanweb;AccountKey=Qku0OcisLL/LFfgZMNHvmQ0PQsYNXIZTL/FbmKDz0XlgqOYpM6M9HMArfUsivJcM/X0o8LeAeZYD+AStouQuZw==;EndpointSuffix=core.windows.net"
                    # Create the BlobServiceClient object which will be used to create a container client
                    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
                    userName = session["userName"]
                    blob_client = blob_service_client.get_blob_client(container="blocksblobforprofilepic", blob=(userName+".jpg"))
                    print("\nUploading to Azure Storage as blob:\n\t" + userName + ".jpg")
                    blob_client.upload_blob(file.stream, overwrite=True)
                    flash("File " + fileName + " uploaded successfully!")
                    server = 'mysqlforweb-123.database.windows.net'
                    database = 'dbforweb'
                    username = 'azureuser'
                    password = '{Hsl@020716}'   
                    driver= '{ODBC Driver 17 for SQL Server}'
                    with pyodbc.connect('DRIVER='+driver+';SERVER=tcp:'+server+';PORT=1433;DATABASE='+database+';UID='+username+';PWD='+ password) as conn:
                        with conn.cursor() as cursor:
                            logger.warning('DB connection established')
                            cursor.execute("UPDATE dbo.UserInfo SET Portrait = 1 WHERE UserName = '" + userName + "'")
                    session["portrait"] = 1
                    return redirect(url_for('mainpage'))
                except Exception as ex:
                    print('Exception:')
                    print(ex)
                    logger.exception('fatal error, blob storage connection failed')
        else:
            print("Invalid action!")
            logger.exception('fatal error, unknown action')
    else:
        session.permanent = True
        if "userName" in session:
            userName = session["userName"]
        else:
            return redirect(url_for('index'))
    if "portrait" in session:
        portrait = session["portrait"]
    if portrait == 0:
        imgurl = "https://storagealanweb.blob.core.windows.net/blocksblobforprofilepic/default.jpg"
    else:
        imgurl = "https://storagealanweb.blob.core.windows.net/blocksblobforprofilepic/" + userName + ".jpg"+"?"+datetime.now().strftime("%Y%m%d%H%M%S")
    print(imgurl)
    return render_template('mainpage.html', userName=userName, imgurl=imgurl)


if __name__ == '__main__':
   app.run()