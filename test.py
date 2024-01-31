#huge drop, 5 days flat, will raise
#volume always peaks at lowest point - look at this data
#   -huge volume increase when dropping significantly or rising significantly
#   -levels out while decreasing until it hits rock bottom where there's another spike
import sqlite3 as sql
#create new database
con = sql.connect("tutorial.db")
#add cursor to navigate db
cur = con.cursor()
#create database cursor w CREATE TAble statement
#cur.execute("CREATE TABLE movie(title,year,score)")
#query the sqlite_master table which now contains an entry for movie table definition
res = cur.execute("SELECT name FROM sqlite_master")
cur.execute("""
    INSERT INTO movie VALUES
        ('Monty Python and the Holy Grail', 1975, 8.2),
        ('And Now for Something Completely Different', 1971, 7.5)
""")
con.commit()

res = cur.execute("SELECT score FROM movie")
res.fetchall()
print(res)








#STORAGE

#use a lot of pandas
#find the best way to store information

#make a huge database of smp500 + bluechip

#yfinance,
    #i think i would only need to store % lower than 95% confidence
        #grab stock history - 2 months??
        #grab stock information
            #avg close of 2 months
            #std dev of 2 months
            #confidence interval =  (std dev * 2)
            #avg - confidence interval = lower 95% ******
            #=1-(current price)/(lower 95% price)
        #grab volume of each day


#DATABASE CREATION

#input list of stock trackers
#write onto database with columns for each thing

#FUNCTIONS
#def confidence(stock)
    #1 ci = std (of 2 months) * 2
    #2 lower_bound = avg(of 2 months) - ci
    #3 percent = 1 - (current price) / lower_bound
#def current_movemement(stock) #for increase
    #store the open data at market open
    #compare to current data, if % change is greater than 2%
    #send email to me
#def day_movement(stock)
    #get last close
    #compare to now
    #if 5%+ drop, email
    #if 5%+ increase, email
#def minimum_price(stock)
    #get close
