import argparse, datetime, json, MySQLdb, oauth2client, operator, os, pytz, requests, smtplib, sys

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
    name, email, appt_type, appt_time, description = "", "", "", "", ""
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
        appt_time = request.form.get("time")
        description = request.form.get("description")
        if name == "" or email == "" or appt_type == "" or appt_time == "" or \
           description == "":
            status = ("ERROR", "Missing some information!")
        elif not recaptcha.verify():
            status = ("ERROR", "Failed robot (aka Turing) test!")
        else:
            credentials = get_credentials()
            http = credentials.authorize(Http())
            service = build('calendar', 'v3', http = http)
            local = pytz.timezone(params["TZ"])
            a, b, c = appt_time.split()
            start = datetime.datetime.strptime("%s %s" %(a, b),
                                               "%Y-%m-%d %H:%M")
            startutc = local.localize(start).isoformat()
            end = datetime.datetime.strptime("%s %s" %(a, c),
                                             "%Y-%m-%d %H:%M")
            endutc = local.localize(end).isoformat()
            event = {
                'summary' : 'Meet %s (Appt. Type: %s)' %(name, appt_type),
                'description' : description,
                'start' : {
                    'dateTime' : startutc
                },
                'end' : {
                    'dateTime' : endutc
                },
            }
            event = service.events().insert(calendarId =
                                            params["CALENDAR_ID"],
                                            body = event).execute()
            cur.execute("""UPDATE TimeSlot SET available = 0 
            WHERE date = %s AND start = %s AND end = %s""", (a, b, c))
            status = ("SUCCESS", "Appointment scheduled successfully and email confirmation sent!")
            g.conn.commit()
            event_id = event.get("id")
            link = "%s/cancel/?date=%s&start=%s&end=%s&event_id=%s" \
                   %(params["URL"], a, b, c, event_id)
            msg = MIMEText("""Dear %s,
            
This is to confirm that you have scheduled the following appointment with me:

~~~
Type: %s
Time: %s
Description: %s 
~~~

To cancel the appointment, please click on the following link or copy and 
paste it into your browser's address bar.

%s

Best,

%s
            """ %(name, appt_type, appt_time, description,
                  link, params["ADMIN_NAME"]))
            msg["Subject"] = "Appointment confirmation"
            msg["From"] = params["ADMIN_EMAIL"]
            msg["To"] = email
            msg["Cc"] = params["ADMIN_EMAIL"]
            s = smtplib.SMTP(params["SMTP_ADDR"])
            s.sendmail(params["ADMIN_EMAIL"], [email, params["ADMIN_EMAIL"]],
                                               msg.as_string())
            s.quit()
            return render_template("success.html", 
                                   params = params,
                                   status = status)
    return render_template("index.html", 
                           params = params,
                           slots = slots,
                           name = name,
                           email = email,
                           appt_type = appt_type,
                           appt_time = appt_time,
                           description = description,
                           status = status)

@app.route("/cancel/", methods = ["GET", "POST"])
def cancel():
    """
    """

    status = ("SUCCESS", "")
    if request.method == "GET":
        cur = g.conn.cursor()
        date = request.args.get('date')
        start = request.args.get('start')
        end = request.args.get('end')
        event_id = request.args.get('event_id')
        credentials = get_credentials()
        http = credentials.authorize(Http())
        service = build('calendar', 'v3', http = http)
        cur.execute("""SELECT count(*) FROM TimeSlot 
            WHERE date = %s AND start = %s AND end = %s""", (date, start, end))
        count = int(cur.fetchone()[0])
        res = service.events().get(calendarId = params["CALENDAR_ID"],
                                   eventId = event_id).execute()
        if count == 0 or res["summary"] == "":
            status = ("ERROR", "Malformed URL, could not cancel appointment!")
        else:
            res = service.events().delete(calendarId = params["CALENDAR_ID"],
                                          eventId = event_id).execute()
            cur.execute("""UPDATE TimeSlot SET available = 1 
            WHERE date = %s AND start = %s AND end = %s""", (date, start, end))
            g.conn.commit()
            status = ("SUCCESS", "Your appointment has been cancelled!")
        return render_template("success.html", 
                               params = params,
                               status = status)

if __name__ == "__main__":
    app.run(debug = True)
