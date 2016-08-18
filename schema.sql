DROP TABLE if exists TimeSlot;

CREATE TABLE TimeSlot (
    date CHAR(10), 
    start CHAR(5),
    end CHAR(5),
    available INTEGER,
    primary key (date, start, end)
);
