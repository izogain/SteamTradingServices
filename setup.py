from distutils.core import setup

setup(
    name="SteamTradeServices",
    version="0.0.1",
    packages=["Exchange"],
    license="",
    author="GTB3NW",
    author_email="ben+steamtradepy@b3nw.me",
    description="A set of services for steam trading",
    install_requires=["pika", "redis", "click", "requests"],
    entry_points={
        "console_scripts": [
            "trade-exchange=Exchange.exchange:main",
        ],
    }
)
