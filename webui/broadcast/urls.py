from django.urls import path

from broadcast.views import compose, confirm, result

app_name = "broadcast"

urlpatterns = [
    path("", compose.compose, name="compose"),
    path("confirm/", confirm.confirm, name="confirm"),
    path("result/", result.result, name="result"),
]
