"""Type annotations and stubs for MechanicalSoup."""
import bs4
import requests


# Extend requests.Response to include the soup attribute that we add
class Response(requests.Response):
    """Extended Response class with soup attribute."""
    soup: bs4.BeautifulSoup | None
