#Steam Trading Services

This project contains a number of services for steam trading which can process or create work queues.

##Trade-Exchange
Trade-Exchange can be run as a service or the class can be instantiated and you can control its functionality
more closely.

Trade-Exchange will **accept**, **decline** and **create** trades. Running the command-line tool "trade-exchange"
(Use the --help option to configuration options) will connect to a local rabbitmq and redis server and start processing
trade requests.

###Auth
The system connects to redis to gain authentication details, any trade-exchange node can access any account in the
redis database, therefore you do not have to specify which trade-exchange node processes which request.

Auth details should be stored with the steamid64 of the account as the key, the value should be a json string in the
following format:

    {
        "api_key": "<YOUR API KEY>",
        "sessionid": "<YOUR SESSION ID COOKIE>",
        "steamLogin": "<YOUR STEAM LOGIN COOKIE>",
        "steamLoginSecure": "<YOUR STEAM LOGIN SECURE COOKIE>",
        "steamMachineAuth<STEAMID64>": "<YOUR STEAM MACHINE AUTH COOKIE>", #The cookie name is suffixed with steamid64
        "steamRememberLogin": "<YOUR STEAM REMEMBER LOGIN COOKIE>"
    }

Please note: Secure your redis database, this is very sensitive information which you do not want exposed!
The cookies can be gathered from your browser. Due to steam restrictions it takes a week for trades to be enabled.
Please plan ahead for your accounts, the last thing you want is to need more accounts and have to wait a week to use
them.

###Queue Processing
To send a request, publish to the exchange named "tradeProcess". Use the following routing keys:

    accept - These requests will be accepted
    decline - These requests will be declined/cancelled
    create - These requests will be created
    
Both accept and decline require the following json strings:

    {
        "steamid64": "<STEAM ID 64>", #ID of your account, not the other user
        "trade_offer_id": "<ID OF TRADE OFFER>"
    }
    
Create trade requires the following json string:

@TODO