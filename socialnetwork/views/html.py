from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from socialnetwork import api
from socialnetwork.api import _get_social_network_user
from socialnetwork.models import SocialNetworkUsers
from socialnetwork.serializers import PostsSerializer
from fame.models import ExpertiseAreas
from fame.models import Fame
from fame.models import FameLevels


@require_http_methods(["GET"])
@login_required
def timeline(request):
    # using the serializer to get the data, then use JSON in the template!
    # avoids having to do the same thing twice

    # initialize community mode to False the first time in the session
    if 'community_mode' not in request.session:
        request.session['community_mode'] = False

    user = _get_social_network_user(request.user)
    community_mode = request.session.get('community_mode', False) # checks if session has a community mode setting, defaults to false if not

    # get extra URL parameters:
    keyword = request.GET.get("search", "")
    published = request.GET.get("published", True)
    error = request.GET.get("error", None)
    

    # if keyword is not empty, use search method of API:
    if keyword and keyword != "":
        context = {
            "posts": PostsSerializer(
                api.search(keyword, published=published), many=True
            ).data,
            "searchkeyword": keyword,
            "error": error,
            "followers": list(api.follows(user).values_list('id', flat=True)),
        }
    else:  # otherwise, use timeline method of API:
        # Get user's communities and eligible communities
        user_communities = user.communities.all()
        
        # Create empty list for eligible communities (user has Super Pro or above fame, i.e. >= 100)
        eligible_communities = []
        # expertise areas where user has fame >= 100:
        eligible_fame = Fame.objects.filter(user=user, fame_level__numeric_value__gte=100).values_list('expertise_area', flat=True)
        # communities where user is not a member but could join
        eligible_communities = ExpertiseAreas.objects.filter(id__in=eligible_fame).exclude(id__in=user_communities)

        context = {
            "posts": PostsSerializer(
                api.timeline(
                    user,
                    published=published,
                    community_mode=community_mode, # include community / normal mode
                ),
                many=True,
            ).data,
            "searchkeyword": "",
            "error": error,
            "followers": list(api.follows(user).values_list('id', flat=True)),
            "community_mode": community_mode,
            "user_communities": user_communities,
            "eligible_communities": eligible_communities,
        }

    return render(request, "timeline.html", context=context)


@require_http_methods(["POST"])
@login_required
def follow(request):
    user = _get_social_network_user(request.user)
    user_to_follow = SocialNetworkUsers.objects.get(id=request.POST.get("user_id"))
    api.follow(user, user_to_follow)
    return redirect(reverse("sn:timeline"))


@require_http_methods(["POST"])
@login_required
def unfollow(request):
    user = _get_social_network_user(request.user)
    user_to_unfollow = SocialNetworkUsers.objects.get(id=request.POST.get("user_id"))
    api.unfollow(user, user_to_unfollow)
    return redirect(reverse("sn:timeline"))


@require_http_methods(["GET"])
@login_required
def bullshitters(request):
    raise NotImplementedError("Not implemented yet")

@require_http_methods(["POST"])
@login_required
def toggle_community_mode(request):
    """Switches between standard and community mode if logged in."""
    request.session['community_mode'] = not request.session.get('community_mode', False)
    return redirect(reverse("sn:timeline"))

@require_http_methods(["POST"])
@login_required
def join_community(request):
    """Adds the user to a community if eligible."""
    user = _get_social_network_user(request.user)
    community_id = request.POST.get("community_id")
    community = ExpertiseAreas.objects.get(id=community_id)
    
    # Check if user has Super Pro or above fame in this expertise area
    fame_entry = Fame.objects.filter(user=user, expertise_area=community).get()
    if fame_entry.fame_level.numeric_value >= 100:
        api.join_community(user, community)
    
    return redirect(reverse("sn:timeline")) # reverse generates the entire URL for the timeline view

@require_http_methods(["POST"])
@login_required
def leave_community(request):
    """Removes the user from a community if they're a member."""
    user = _get_social_network_user(request.user)
    community_id = request.POST.get("community_id")
    community = ExpertiseAreas.objects.get(id=community_id)
    
    # Check if user is member of that community
    if user.communities.filter(id=community.id).exists():
        api.leave_community(user, community)
    
    return redirect(reverse("sn:timeline")) # reverse generates the entire URL for the timeline view

@require_http_methods(["GET"])
@login_required
def similar_users(request):
    """Displays similar user for the user if logged in."""
    user = _get_social_network_user(request.user) # user object of the current user
    similar_users_qs = api.similar_users(user) # user objects that are similar according to the similar users api

    # context: content that should be inserted into the html template
    context = {
        "similar_users": similar_users_qs,
    }

    return render(request, "similar_users.html", context=context)
