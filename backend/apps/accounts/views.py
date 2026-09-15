from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.services import log_action

from .models import Role, User
from .permissions import HasPermission
from .serializers import (
    LoginSerializer,
    PasswordResetSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            log_action(
                action="auth.login_failed",
                request=request,
                metadata={"username": request.data.get("username", "")},
            )
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        log_action(user=user, action="auth.login", request=request)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or already blacklisted token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_action(user=request.user, action="auth.logout", request=request)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class RoleListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission("user.manage")]
    serializer_class = RoleSerializer
    queryset = Role.objects.prefetch_related("permissions").all()


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("user.manage")]
    queryset = User.objects.select_related("role").all().order_by("username")

    def get_serializer_class(self):
        return UserCreateSerializer if self.request.method == "POST" else UserSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = UserCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        user = input_serializer.save()
        log_action(
            user=request.user,
            action="user.created",
            request=request,
            metadata={"target_user_id": user.id, "username": user.username},
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, HasPermission("user.manage")]
    queryset = User.objects.select_related("role").all()

    def get_serializer_class(self):
        return UserUpdateSerializer if self.request.method in ("PUT", "PATCH") else UserSerializer

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        input_serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        input_serializer.is_valid(raise_exception=True)
        input_serializer.save()
        log_action(
            user=request.user,
            action="user.updated",
            request=request,
            metadata={"target_user_id": user.id, "changed_fields": list(request.data.keys())},
        )
        return Response(UserSerializer(user).data)


class UserActivateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("user.manage")]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        user.is_active = True
        user.save(update_fields=["is_active"])
        log_action(
            user=request.user,
            action="user.activated",
            request=request,
            metadata={"target_user_id": user.id, "username": user.username},
        )
        return Response(UserSerializer(user).data)


class UserDeactivateView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("user.manage")]

    def post(self, request, pk):
        if str(request.user.pk) == str(pk):
            return Response(
                {"detail": "Anda tidak bisa menonaktifkan akun sendiri."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        user.is_active = False
        user.save(update_fields=["is_active"])
        log_action(
            user=request.user,
            action="user.deactivated",
            request=request,
            metadata={"target_user_id": user.id, "username": user.username},
        )
        return Response(UserSerializer(user).data)


class UserResetPasswordView(APIView):
    permission_classes = [IsAuthenticated, HasPermission("user.manage")]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        log_action(
            user=request.user,
            action="user.password_reset",
            request=request,
            metadata={"target_user_id": user.id, "username": user.username},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
