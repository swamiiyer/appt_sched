# 
#
# Usage: python manage_time_slots.py [-l]

import datetime, json, MySQLdb, operator, sys

def main(args):
    read_only = len(args) == 1 and args[0] == "-l"
    params = json.load(open("params.json", "r"))
    conn = MySQLdb.connect(host = "localhost", 
                           user = params["DB_USER"], 
                           db = params["DB_NAME"])
    cur = conn.cursor()
    if read_only:
        now = datetime.datetime.now()
        nowdatestr = "%04d-%02d-%02d" %(now.year, now.month, now.day)
        nowtimestr = "%04d-%02d-%02d %02d:%02d" \
                     %(now.year, now.month, now.day, now.hour, now.minute)
        cur.execute("""SELECT * FROM TimeSlot""")
        slots = {}
        for date, start, end, available in cur.fetchall():
            if date + " " + start > nowtimestr:
                slots.setdefault(date, [])
                slots[date].append((start, end, available))
        for date in slots.keys():
            slots[date].sort(key = operator.itemgetter(0))
        for date in sorted(slots.keys()):
            a, b, c = map(int, date.split("-"))
            datestr = datetime.datetime(a, b, c).strftime("%b %d (%a) %Y")
            print(datestr)
            for start, end, available in slots[date]:
                if available:
                    print("  %s - %s (*)" %(start, end))
                else:
                    print("  %s - %s" %(start, end))
    else:
        lines = sys.stdin.readlines()
        for i, line in enumerate(lines):
            date, start, end, command = line.strip().split()
            if command == "+":
                cur.execute("""INSERT IGNORE INTO TimeSlot 
                VALUES (%s, %s, %s, 1)""", (date, start, end))
            elif command == "-":
                cur.execute("""DELETE FROM TimeSlot 
                WHERE date = %s AND start = %s AND end = %s""",
                            (date, start, end))
            else:
                print("Error: invalid command %s on line %d" % (command, i + 1))
        conn.commit()
    conn.close()

if __name__ == "__main__":
    main(sys.argv[1:])
