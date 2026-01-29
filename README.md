# csci-5673-assignment

Initialize the database by executing:
```
mysql -u root -p < db/schema.sql
```

Install the required packages:
```
pip install -r requirements.txt
```

Start the socket server:
```
python .\server\buyer\buyer.py
```

Start the client:
```
python .\client\buyer\buyer.py
```
