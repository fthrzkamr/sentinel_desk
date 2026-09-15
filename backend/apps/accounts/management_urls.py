from django.urls import path

from .views import (
    RoleListView,
    UserActivateView,
    UserDeactivateView,
    UserDetailView,
    UserListCreateView,
    UserResetPasswordView,
)

urlpatterns = [
    path("roles/", RoleListView.as_view(), name="role-list"),
    path("users/", UserListCreateView.as_view(), name="user-list-create"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/<int:pk>/activate/", UserActivateView.as_view(), name="user-activate"),
    path("users/<int:pk>/deactivate/", UserDeactivateView.as_view(), name="user-deactivate"),
    path("users/<int:pk>/reset-password/", UserResetPasswordView.as_view(), name="user-reset-password"),
]
