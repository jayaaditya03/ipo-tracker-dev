from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    25 per page by default; the client may ask for up to 100 with
    ?page_size= — enough for a picker without unbounded responses.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
