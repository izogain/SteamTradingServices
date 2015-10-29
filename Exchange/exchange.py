from pika.exceptions import ConnectionClosed as pikaConnectionClosed
from redis.exceptions import ConnectionError as redisConnectionError
import sys
import logging
import click
import pika
import redis
import json
import requests
import threading

log = logging.getLogger(__name__)
debug_mode = False


@click.command()
@click.option("--debug", is_flag=True, help="Enable debugging")
@click.option("--rmqhost", default="localhost", help="Rabbitmq host details")
@click.option("--redishost", default="localhost", help="Redis host details")
@click.option("--redisport", default=6379, help="Redis port details")
@click.option("--redisdb", default=0, help="Redis db details")
@click.option("--status", is_flag=True, help="Distribute status information to status exchange")
@click.option("--publishresult", is_flag=True, help="Publish result of trade")
def main(debug, rmqhost, redishost, redisport, redisdb, status, publishresult):
    """
    trade-exchange is a service designed to accept, decline and create trades in steam.
    It connects to a work queue and processes it, therefore multiple processes can be
    created to process the trade queues as long as the authentication details are available.
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG)
        global debug_mode
        debug_mode = True
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        Exchange(rmqhost, redishost, redisport, redisdb, status, publishresult).consume()
    except KeyboardInterrupt:
        log.warning("Received keyboard interrupt, exiting!")
        sys.exit(0)
    except pikaConnectionClosed:
        log.error("Couldn't connect to rabbitmq, exiting!")
        sys.exit(1)
    except redisConnectionError:
        log.error("Couldn't connect to redis, exiting!")
        sys.exit(1)

    pass


class Exchange:
    def __init__(self, rmqhost, redishost, redisport, redisdb, status, publishresult):
        self.rmqhost = rmqhost
        self.redishost = redishost
        self.redisport = redisport
        self.redisdb = redisdb
        self.status = status
        self.publishresult = publishresult
        self.lock = threading.Lock()

        log.info("Exchange Service is starting")
        log.debug("Connecting to rabbitmq on " + self.rmqhost)

        self.rmq_connection = pika.BlockingConnection(pika.ConnectionParameters(self.rmqhost))
        self.rmq_channel = self.rmq_connection.channel()

        log.debug("Connected to rabbitmq")
        log.debug("Connecting to redis on " + self.redishost + ":" + self.redisport + " db: " + self.redisdb)

        self.redis_connection = redis.StrictRedis(host=self.redishost, port=self.redisport, db=self.redisdb)
        self.redis_connection.ping()

        if publishresult:
            self.rmq_channel.exchange_declare(exchange="tradeResults", exchange_type="direct")

        log.debug("Connected to redis")
        pass

    def _get_auth(self, steamid64):
        return self.redis_connection.get(steamid64)
        pass

    def accept_trade(self, request):
        cookies = self._get_auth(request["steamid64"])

        header = {
            "Origin": "https://steamcommunity.com",
            "Referer": "https://steamcommunity.com/tradeoffer/" + str(request["trade_offer_id"]) + "/"
        }

        data = {
            "sessionid": cookies["sessionid"],
            "serverid": "1",
            "tradeofferid": request["trade_offer_id"]
        }

        cookies.remove("api_key")

        return requests.post("https://steamcommunity.com/tradeoffer/" + str(request["trade_offer_id"]) + "/accept",
                              headers=header, cookies=cookies, data=data).json()
        pass

    def decline_trade(self, request):
        cookies = self._get_auth(request["steamid64"])

        data = {
            "key": cookies["api_key"],
            "tradeofferid": request["trade_offer_id"]
        }

        return requests.post("https://api.steampowered.com/IEconService/DeclineTradeOffer/v1/", data=data).json()
        pass

    def create_trade(self, request):
        cookies = self._get_auth(request["steamid64"])

        header = {
            "Origin": "https://steamcommunity.com",
            "Referer": "https://steamcommunity.com/tradeoffer/new/?partner=" + str(request["partner_id_short"])
        }

        data = {
            "sessionid": cookies["sessionid"],
            "serverid": "1",
            "partner": request["partner_id_long"],
            "tradeoffermessage": request["trade_message"],
            "captcha": "",
            "trade_offer_create_params": {},
            "json_tradeoffer": request["trade"]
        }

        if request["trade_token"]:
            header["Referer"] = header["Referer"] + str("&token=") + str(request["trade_token"])
            data["trade_offer_create_params"] = "{\"trade_offer_access_token\":\"" + str(request["trade_token"]) + "\"}"

        cookies.remove("api_key")

        return requests.post("https://steamcommunity.com/tradeoffer/new/send",
                             headers=header, cookies=cookies, data=data)
        pass

    def consume(self):
        def _thread_by_proxy(method_to_exec, request, type, method, callback):

            # TODO: publish status

            response = method_to_exec(request)

            self.lock.acquire()
            self.rmq_channel.basic_ack(delivery_tag=method.delivery_tag)
            callback(response)
            self.lock.release()
            pass

        def _accept_callback(response):
            if self.publishresult:
                self.rmq_channel.basic_publish("tradeResults", "accept", str(response))
            pass

        def _decline_callback(response):
            if self.publishresult:
                self.rmq_channel.basic_publish("tradeResults", "decline", str(response))
            pass

        def _create_callback(response):
            if self.publishresult:
                self.rmq_channel.basic_publish("tradeResults", "create", str(response))
            pass

        def _accept_consume(self, ch, method, properties, body):
            msg = json.loads(body.decode("utf-8"))
            threading.Thread(target=_thread_by_proxy, args=(self.accept_trade, msg, method, _accept_callback))
            pass

        def _decline_consume(self, ch, method, properties, body):
            msg = json.loads(body.decode("utf-8"))
            threading.Thread(target=_thread_by_proxy, args=(self.decline_trade, msg, method, _decline_callback))
            pass

        def _create_consume(self, ch, method, properties, body):
            msg = json.loads(body.decode("utf-8"))
            threading.Thread(target=_thread_by_proxy, args=(self.create_trade, msg, method, _create_callback))
            pass

        log.debug("Creating exchanges")

        if self.status:
            self.rmq_channel.exchange_declare(exchange="status", exchange_type="topic")

        self.rmq_channel.exchange_declare(exchange="tradeProcess", exchange_type="direct")
        self.rmq_channel.queue_declare(queue="tradeAccept")
        self.rmq_channel.queue_declare(queue="tradeDecline")
        self.rmq_channel.queue_declare(queue="tradeCreate")
        self.rmq_channel.queue_bind("tradeAccept", "tradeProcess", routing_key="accept")
        self.rmq_channel.queue_bind("tradeDecline", "tradeProcess", routing_key="decline")
        self.rmq_channel.queue_bind("tradeCreate", "tradeProcess", routing_key="create")

        log.info("Everything is connected, starting consume loops..")

        self.rmq_channel.basic_consume(_accept_consume, "tradeAccept")
        self.rmq_channel.basic_consume(_decline_consume, "tradeDecline")
        self.rmq_channel.basic_consume(_create_consume, "tradeCreate")

        pass
