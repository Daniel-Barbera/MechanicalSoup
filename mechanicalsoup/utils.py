from bs4 import Tag


class LinkNotFoundError(Exception):
    """Exception raised when mechanicalsoup fails to find something.

    This happens in situations like (non-exhaustive list):

    * :func:`~mechanicalsoup.StatefulBrowser.find_link` is called, but
      no link is found.

    * The browser was configured with raise_on_404=True and a 404
      error is triggered while browsing.

    * The user tried to fill-in a field which doesn't exist in a form
      (e.g. browser["name"] = "val" with browser being a
      StatefulBrowser).
    """
    pass


def is_multipart_file_upload(form: Tag, tag: Tag) -> bool:
    enctype = form.get("enctype", "")
    tag_type = tag.get("type", "")
    if not isinstance(enctype, str) or not isinstance(tag_type, str):
        return False
    return (
        enctype == "multipart/form-data" and
        tag_type.lower() == "file"
    )
