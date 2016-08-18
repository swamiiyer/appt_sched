import argparse, datetime, json, MySQLdb, oauth2client, operator, os, pickle, requests, smtplib, sys

from apiclient.discovery import build
from httplib2 import Http
from oauth2client import client, file, tools
from email.mime.text import MIMEText
from flask import abort, Flask, g, render_template, redirect, request, \
    Response, session, url_for
from werkzeug import secure_filename
from flask_recaptcha import ReCaptcha

dirname = os.path.dirname(os.path.abspath(__file__))
params = json.load(open("%s/params.json" %(dirname), "r"))
app = Flask(__name__)
app.config.from_object(__name__)
app.config["RECAPTCHA_ENABLED"] = True
app.config["RECAPTCHA_SITE_KEY"] = params["RC_SITE_KEY"]
app.config["RECAPTCHA_SECRET_KEY"] = params["RC_SECRET_KEY"]
recaptcha = ReCaptcha(app = app)

def get_credentials():
    """
    """

    scopes = "https://www.googleapis.com/auth/calendar"
    client_secret_file = "%s/client_secret.json" %(dirname)
    store = file.Storage("%s/storage.json" %(dirname))
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(client_secret_file, scopes)
        flags = argparse.ArgumentParser(parents =
                                        [tools.argparser]).parse_args()
        credentials = tools.run_flow(flow, store, flags)
    return credentials

@app.template_filter("prettydate")
def prettydate_filter(str):
    """
    Converts str storing date/time information in "1998-06-06" format 
    to "Jun 06 (Sat) 1998" format and returns the value.
    """

    a, b, c = map(int, str.split("-"))
    x = datetime.datetime(a, b, c)
    return x.strftime("%b %d (%a) %Y")

@app.before_request
def before_request():
    """
    Called before each request.
    """

    g.conn = MySQLdb.connect(host = "localhost", 
                             user = params["DB_USER"], 
                             db = params["DB_NAME"],
                             connect_timeout = 10)

@app.teardown_request
def teardown_request(exception):
    """
    Called after each request.
    """

    conn = getattr(g, "conn", None)
    if conn is not None:
        conn.close()
    
@app.route("/", methods = ["GET", "POST"])
def index():
    """
    """

    status = ("SUCCESS", "")
    slots = {}
    now = datetime.datetime.now()
    nowdatestr = "%04d-%02d-%02d" %(now.year, now.month, now.day)
    nowtimestr = "%04d-%02d-%02d %02d:%02d" \
                 %(now.year, now.month, now.day, now.hour, now.minute)
    cur = g.conn.cursor()
    cur.execute("""SELECT * FROM TimeSlot""")
    slots = {}
    for date, start, end, available in cur.fetchall():
        if date + " " + start > nowtimestr and available == 1:
            slots.setdefault(date, [])
            slots[date].append((start, end))
    for date in slots.keys():
        slots[date].sort(key = operator.itemgetter(0))
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        appt_type = request.form.get("type")
        appt_time = request.form.getlist("time")
        description = request.form.get("description")
        print name, email, appt_type, appt_time, description
        if name == "" or email == "" or appt_type == "" or len(appt_time) == 0:
            status = ("ERROR", "Required field(s) missing!")
        elif not recaptcha.verify():
            status = ("ERROR", "You are a robot!")
        else:
            credentials = get_credentials()
            http = credentials.authorize(Http())
            service = build('calendar', 'v3', http = http)
            for time in appt_time:
                a, b, c = time.split()
                event = {
                    'summary' : '%s appointment with %s' %(appt_type, name),
                    'description' : description,
                    'start' : {
                        'dateTime' : '%sT%s:00-04:00' %(a, b)
                    },
                    'end' : {
                        'dateTime' : '%sT%s:00-04:00' %(a, c)
                    },
                }
                event = service.events().insert(calendarId =
                                                params["CALENDAR_ID"],
                                                body = event).execute()
                cur.execute("""UPDATE TimeSlot SET available = 0 
                WHERE date = %s AND start = %s AND end = %s""", (a, b, c))
                status = ("SUCCESS", "Appointment scheduled successfully and email confirmation sent!")
                g.conn.commit()
                return render_template("index2.html", 
                                       params = params,
                                       slots = slots,
                                       status = status)
    return render_template("index.html", 
                           params = params,
                           slots = slots,
                           status = status)

if __name__ == "__main__":
    app.run(debug = True)
