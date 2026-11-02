from rest_framework.pagination import PageNumberPagination
from rest_framework.utils.urls import remove_query_param, replace_query_param


class DefaultPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 500

    # Deliberately relative (path + query only, no scheme/host): the dev
    # frontend reaches this API through Vite's proxy with changeOrigin=true,
    # which rewrites the Host header the backend sees to the internal Docker
    # service name (e.g. "backend:8000") — build_absolute_uri() would bake
    # that unreachable-from-the-browser host straight into next/previous,
    # silently breaking pagination the moment a client actually follows the
    # link. get_full_path() sidesteps the Host header entirely.
    def get_next_link(self):
        if not self.page.has_next():
            return None
        url = self.request.get_full_path()
        page_number = self.page.next_page_number()
        return replace_query_param(url, self.page_query_param, page_number)

    def get_previous_link(self):
        if not self.page.has_previous():
            return None
        url = self.request.get_full_path()
        page_number = self.page.previous_page_number()
        if page_number == 1:
            return remove_query_param(url, self.page_query_param)
        return replace_query_param(url, self.page_query_param, page_number)
