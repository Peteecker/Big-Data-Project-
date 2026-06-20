from django.urls import path

from socialnetwork.views.html import timeline
from socialnetwork.views.html import follow
from socialnetwork.views.html import unfollow
from socialnetwork.views.html import similar_users
from socialnetwork.views.html import join_community
from socialnetwork.views.html import leave_community
from socialnetwork.views.html import toggle_community_mode
from socialnetwork.views.html import bullshitters
from socialnetwork.views.rest import PostsListApiView

app_name = "socialnetwork"

urlpatterns = [
    path("api/posts", PostsListApiView.as_view(), name="posts_fulllist"),
    path("html/timeline", timeline, name="timeline"),
    path("api/follow", follow, name="follow"),
    path("api/unfollow", unfollow, name="unfollow"),
    path("html/similar_users", similar_users, name="similar_users"),
    path("html/join_community", join_community, name="join_community"),
    path("html/leave_community", leave_community, name="leave_community"),
    path("html/toggle_community_mode", toggle_community_mode, name="toggle_community_mode"),
    path("html/bullshitters", bullshitters, name="bullshitters"),
]
