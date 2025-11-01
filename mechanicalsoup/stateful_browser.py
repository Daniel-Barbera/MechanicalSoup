import re
import sys
import urllib
from typing import Any, cast

import bs4
from bs4 import Tag
import requests

from .browser import Browser
from .form import Form
from .utils import LinkNotFoundError
from ._types import Response

from requests.structures import CaseInsensitiveDict


class _BrowserState:
    def __init__(
        self,
        page: bs4.BeautifulSoup | None = None,
        url: str | None = None,
        form: Form | None = None,
        request: requests.PreparedRequest | None = None
    ) -> None:
        self.page: bs4.BeautifulSoup | None = page
        self.url: str | None = url
        self.form: Form | None = form
        self.request: requests.PreparedRequest | None = request


class StatefulBrowser(Browser):
    """An extension of :class:`Browser` that stores the browser's state
    and provides many convenient functions for interacting with HTML elements.
    It is the primary tool in MechanicalSoup for interfacing with websites.

    :param session: Attach a pre-existing requests Session instead of
        constructing a new one.
    :param soup_config: Configuration passed to BeautifulSoup to affect
        the way HTML is parsed. Defaults to ``{'features': 'lxml'}``.
        If overridden, it is highly recommended to `specify a parser
        <https://www.crummy.com/software/BeautifulSoup/bs4/doc/#specifying-the-parser-to-use>`__.
        Otherwise, BeautifulSoup will issue a warning and pick one for
        you, but the parser it chooses may be different on different
        machines.
    :param requests_adapters: Configuration passed to requests, to affect
        the way HTTP requests are performed.
    :param raise_on_404: If True, raise :class:`LinkNotFoundError`
        when visiting a page triggers a 404 Not Found error.
    :param user_agent: Set the user agent header to this value.

    All arguments are forwarded to :func:`Browser`.

    Examples ::

        browser = mechanicalsoup.StatefulBrowser(
            soup_config={'features': 'lxml'},  # Use the lxml HTML parser
            raise_on_404=True,
            user_agent='MyBot/0.1: mysite.example.com/bot_info',
        )
        browser.open(url)
        # ...
        browser.close()

    Once not used anymore, the browser can be closed
    using :func:`~Browser.close`.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__debug: bool = False
        self.__verbose: int = 0
        self.__state: _BrowserState = _BrowserState()

        # Aliases for backwards compatibility
        # (Included specifically in __init__ to suppress them in Sphinx docs)
        self.get_current_page = lambda: self.page
        # Almost same as self.form, but don't raise an error if no
        # form was selected for backward compatibility.
        self.get_current_form = lambda: self.__state.form
        self.get_url = lambda: self.url

    def set_debug(self, debug: bool) -> None:
        """Set the debug mode (off by default).

        Set to True to enable debug mode. When active, some actions
        will launch a browser on the current page on failure to let
        you inspect the page content.
        """
        self.__debug = debug

    def get_debug(self) -> bool:
        """Get the debug mode (off by default)."""
        return self.__debug

    def set_verbose(self, verbose: int) -> None:
        """Set the verbosity level (an integer).

        * 0 means no verbose output.
        * 1 shows one dot per visited page (looks like a progress bar)
        * >= 2 shows each visited URL.
        """
        self.__verbose = verbose

    def get_verbose(self) -> int:
        """Get the verbosity level. See :func:`set_verbose()`."""
        return self.__verbose

    @property
    def page(self) -> bs4.BeautifulSoup | None:
        """Get the current page as a soup object."""
        return self.__state.page

    @property
    def url(self) -> str | None:
        """Get the URL of the currently visited page."""
        return self.__state.url

    @property
    def form(self) -> Form:
        """Get the currently selected form as a :class:`Form` object.
        See :func:`select_form`.
        """
        if self.__state.form is None:
            raise AttributeError("No form has been selected yet on this page.")
        return self.__state.form

    def __setitem__(self, name: str, value: Any) -> None:
        """Call item assignment on the currently selected form.
        See :func:`Form.__setitem__`.
        """
        self.form[name] = value

    def new_control(
        self, type: str, name: str, value: Any, **kwargs: Any
    ) -> Tag:
        """Call :func:`Form.new_control` on the currently selected form."""
        return self.form.new_control(type, name, value, **kwargs)

    def absolute_url(self, url: str) -> str:
        """Return the absolute URL made from from the current URL and ``url``.
        The current URL is only used to provide any missing components of
        ``url``, as in the `.urljoin() method of urllib.parse
        <https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urljoin>`__.
        """
        current_url = self.url or ""
        return urllib.parse.urljoin(current_url, url)

    def open(self, url: str, *args: Any, **kwargs: Any) -> Response:
        """Open the URL and store the Browser's state in this object.
        All arguments are forwarded to :func:`Browser.get`.

        :return: Forwarded from :func:`Browser.get`.
        """
        if self.__verbose == 1:
            sys.stdout.write('.')
            sys.stdout.flush()
        elif self.__verbose >= 2:
            print(url)

        resp = self.get(url, *args, **kwargs)
        self.__state = _BrowserState(page=resp.soup, url=resp.url,
                                     request=resp.request)
        return resp

    def open_fake_page(
        self,
        page_text: str,
        url: str | None = None,
        soup_config: dict[str, Any] | None = None
    ) -> None:
        """Mock version of :func:`open`.

        Behave as if opening a page whose text is ``page_text``, but do not
        perform any network access. If ``url`` is set, pretend it is the page's
        URL. Useful mainly for testing.
        """
        soup_config = soup_config or self.soup_config
        self.__state = _BrowserState(
            page=bs4.BeautifulSoup(page_text, **soup_config),
            url=url)

    def open_relative(
        self, url: str, *args: Any, **kwargs: Any
    ) -> Response:
        """Like :func:`open`, but ``url`` can be relative to the currently
        visited page.
        """
        return self.open(self.absolute_url(url), *args, **kwargs)

    def refresh(self) -> Response:
        """Reload the current page with the same request as originally done.
        Any change (`select_form`, or any value filled-in in the form) made to
        the current page before refresh is discarded.

        :raise ValueError: Raised if no refreshable page is loaded, e.g., when
            using the shallow ``Browser`` wrapper functions.

        :return: Response of the request."""
        old_request = self.__state.request
        if old_request is None:
            raise ValueError('The current page is not refreshable. Either no '
                             'page is opened or low-level browser methods '
                             'were used to do so')

        if not self.session:
            raise RuntimeError("Session is closed")
        resp = cast(Response, self.session.send(old_request))
        Browser.add_soup(resp, self.soup_config)
        self.__state = _BrowserState(page=resp.soup, url=resp.url,
                                     request=resp.request)
        return resp

    def select_form(self, selector: str | Tag = "form", nr: int = 0) -> Form:
        """Select a form in the current page.

        :param selector: CSS selector or a bs4.element.Tag object to identify
            the form to select.
            If not specified, ``selector`` defaults to "form", which is
            useful if, e.g., there is only one form on the page.
            For ``selector`` syntax, see the `.select() method in BeautifulSoup
            <https://www.crummy.com/software/BeautifulSoup/bs4/doc/#css-selectors>`__.
        :param nr: A zero-based index specifying which form among those that
            match ``selector`` will be selected. Useful when one or more forms
            have the same attributes as the form you want to select, and its
            position on the page is the only way to uniquely identify it.
            Default is the first matching form (``nr=0``).

        :return: The selected form as a soup object. It can also be
            retrieved later with the :attr:`form` attribute.
        """

        def find_associated_elements(form_id: str) -> list[Tag]:
            """Find all elements associated to a form
                (i.e. an element with a form attribute -> ``form=form_id``)
            """

            # Elements which can have a form owner
            elements_with_owner_form = ("input", "button", "fieldset",
                                        "object", "output", "select",
                                        "textarea")

            found_elements: list[Tag] = []

            page = self.page
            if not page:
                return found_elements

            for element in elements_with_owner_form:
                found_elements.extend(
                    [e for e in page.find_all(element, form=form_id)
                     if isinstance(e, Tag)]
                )
            return found_elements

        if isinstance(selector, bs4.element.Tag):
            if selector.name != "form":
                raise LinkNotFoundError
            form = selector
        else:
            # nr is a 0-based index for consistency with mechanize
            page = self.page
            if not page:
                raise LinkNotFoundError("No page loaded")
            found_forms = page.select(selector, limit=nr + 1)
            if len(found_forms) != nr + 1:
                if self.__debug:
                    print('select_form failed for', selector)
                    self.launch_browser()
                raise LinkNotFoundError()

            form = found_forms[-1]

        if form and form.has_attr('id'):
            form_id_val = form["id"]
            if isinstance(form_id_val, str):
                form_id = form_id_val
                new_elements = find_associated_elements(form_id)
                form.extend(new_elements)

        self.__state.form = Form(form)

        return self.form

    def _merge_referer(self, **kwargs: Any) -> dict[str, Any]:
        """Helper function to set the Referer header in kwargs passed to
        requests, if it has not already been overridden by the user."""

        referer = self.url
        headers = CaseInsensitiveDict(kwargs.get('headers', {}))
        if referer is not None and 'Referer' not in headers:
            headers['Referer'] = referer
            kwargs['headers'] = headers
        return kwargs

    def submit_selected(
        self,
        btnName: Tag | str | None | bool = None,
        update_state: bool = True,
        **kwargs: Any
    ) -> Response:
        """Submit the form that was selected with :func:`select_form`.

        :return: Forwarded from :func:`Browser.submit`.

        :param btnName: Passed to :func:`Form.choose_submit` to choose the
            element of the current form to use for submission. If ``None``,
            will choose the first valid submit element in the form, if one
            exists. If ``False``, will not use any submit element; this is
            useful for simulating AJAX requests, for example.

        :param update_state: If False, the form will be submitted but the
            browser state will remain unchanged; this is useful for forms that
            result in a download of a file, for example.

        All other arguments are forwarded to :func:`Browser.submit`.
        """
        self.form.choose_submit(btnName)

        kwargs = self._merge_referer(**kwargs)
        form_obj = self.__state.form
        if not form_obj:
            raise AttributeError("No form has been selected")
        resp = self.submit(form_obj, url=self.__state.url, **kwargs)
        if update_state:
            self.__state = _BrowserState(page=resp.soup, url=resp.url,
                                         request=resp.request)
        return resp

    def list_links(self, *args: Any, **kwargs: Any) -> None:
        """Display the list of links in the current page. Arguments are
        forwarded to :func:`links`.
        """
        print("Links in the current page:")
        for link in self.links(*args, **kwargs):
            print("    ", link)

    def links(
        self,
        url_regex: str | None = None,
        link_text: str | None = None,
        *args: Any,
        **kwargs: Any
    ) -> list[Tag]:
        """Return links in the page, as a list of bs4.element.Tag objects.

        To return links matching specific criteria, specify ``url_regex``
        to match the *href*-attribute, or ``link_text`` to match the
        *text*-attribute of the Tag. All other arguments are forwarded to
        the `.find_all() method in BeautifulSoup
        <https://www.crummy.com/software/BeautifulSoup/bs4/doc/#find-all>`__.
        """
        page = self.page
        if not page:
            return []
        all_links = page.find_all('a', href=True, *args, **kwargs)
        result: list[Tag] = [
            link for link in all_links if isinstance(link, Tag)
        ]
        if url_regex is not None:
            result = [
                a for a in result
                if (isinstance(a['href'], str) and
                    re.search(url_regex, a['href']))
            ]
        if link_text is not None:
            result = [a for a in result if a.text == link_text]
        return result

    def find_link(self, *args: Any, **kwargs: Any) -> Tag:
        """Find and return a link, as a bs4.element.Tag object.

        The search can be refined by specifying any argument that is accepted
        by :func:`links`. If several links match, return the first one found.

        If no link is found, raise :class:`LinkNotFoundError`.
        """
        links = self.links(*args, **kwargs)
        if len(links) == 0:
            raise LinkNotFoundError()
        else:
            return links[0]

    def _find_link_internal(
        self,
        link: Tag | str | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any]
    ) -> Tag:
        """Wrapper around find_link that deals with convenience special-cases:

        * If ``link`` has an *href*-attribute, then return it. If not,
          consider it as a ``url_regex`` argument.

        * If searching for the link fails and debug is active, launch
          a browser.
        """
        if isinstance(link, Tag) and 'href' in link.attrs:
            return link

        # Check if "link" parameter should be treated as "url_regex"
        # but reject obtaining it from both places.
        if link and 'url_regex' in kwargs:
            raise ValueError('link parameter cannot be treated as '
                             'url_regex because url_regex is already '
                             'present in keyword arguments')
        elif link:
            kwargs['url_regex'] = link

        try:
            return self.find_link(*args, **kwargs)
        except LinkNotFoundError:
            if self.get_debug():
                print('find_link failed for', kwargs)
                self.list_links()
                self.launch_browser()
            raise

    def follow_link(
        self,
        link: Tag | str | None = None,
        *bs4_args: Any,
        bs4_kwargs: dict[str, Any] = {},
        requests_kwargs: dict[str, Any] = {},
        **kwargs: Any
    ) -> Response:
        """Follow a link.

        If ``link`` is a bs4.element.Tag (i.e. from a previous call to
        :func:`links` or :func:`find_link`), then follow the link.

        If ``link`` doesn't have a *href*-attribute or is None, treat
        ``link`` as a url_regex and look it up with :func:`find_link`.
        ``bs4_kwargs`` are forwarded to :func:`find_link`.
        For backward compatibility, any excess keyword arguments
        (aka ``**kwargs``)
        are also forwarded to :func:`find_link`.

        If the link is not found, raise :class:`LinkNotFoundError`.
        Before raising, if debug is activated, list available links in the
        page and launch a browser.

        ``requests_kwargs`` are forwarded to :func:`open_relative`.

        :return: Forwarded from :func:`open_relative`.
        """
        link_tag = self._find_link_internal(link, bs4_args,
                                            {**bs4_kwargs, **kwargs})

        requests_kwargs = self._merge_referer(**requests_kwargs)

        href = link_tag['href']
        if isinstance(href, list):
            href = href[0] if href else ""
        return self.open_relative(str(href), **requests_kwargs)

    def download_link(
        self,
        link: Tag | str | None = None,
        file: str | None = None,
        *bs4_args: Any,
        bs4_kwargs: dict[str, Any] = {},
        requests_kwargs: dict[str, Any] = {},
        **kwargs: Any
    ) -> requests.Response:
        """Downloads the contents of a link to a file. This function behaves
        similarly to :func:`follow_link`, but the browser state will
        not change when calling this function.

        :param file: Filesystem path where the page contents will be
            downloaded. If the file already exists, it will be overwritten.

        Other arguments are the same as :func:`follow_link` (``link``
        can either be a bs4.element.Tag or a URL regex.
        ``bs4_kwargs`` arguments are forwarded to :func:`find_link`,
        as are any excess keyword arguments (aka ``**kwargs``) for backwards
        compatibility).

        :return: `requests.Response
            <http://docs.python-requests.org/en/master/api/#requests.Response>`__
            object.
        """
        link_tag = self._find_link_internal(link, bs4_args,
                                            {**bs4_kwargs, **kwargs})
        href = link_tag['href']
        if isinstance(href, list):
            href = href[0] if href else ""
        url = self.absolute_url(str(href))

        requests_kwargs = self._merge_referer(**requests_kwargs)

        if not self.session:
            raise RuntimeError("Session is closed")
        response = self.session.get(url, **requests_kwargs)
        if self.raise_on_404 and response.status_code == 404:
            raise LinkNotFoundError()

        # Save the response content to file
        if file is not None:
            with open(file, 'wb') as f:
                f.write(response.content)

        return response

    def launch_browser(self, soup: bs4.BeautifulSoup | None = None) -> None:
        """Launch a browser to display a page, for debugging purposes.

        :param: soup: Page contents to display, supplied as a bs4 soup object.
            Defaults to the current page of the ``StatefulBrowser`` instance.
        """
        if soup is None:
            soup = self.page
        if soup is None:
            raise ValueError("No page to display")
        super().launch_browser(soup)
