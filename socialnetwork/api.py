from django.db.models import Q, Exists, OuterRef, When, IntegerField, FloatField, Count, ExpressionWrapper, Case, Value, F, Prefetch

from fame.models import Fame, FameLevels, FameUsers, ExpertiseAreas
from socialnetwork.models import Posts, SocialNetworkUsers


# general methods independent of html and REST views
# should be used by REST and html views


def _get_social_network_user(user) -> SocialNetworkUsers:
    """Given a FameUser, gets the social network user from the request. Assumes that the user is authenticated."""
    try:
        user = SocialNetworkUsers.objects.get(id=user.id)
    except SocialNetworkUsers.DoesNotExist:
        raise PermissionError("User does not exist")
    return user


def timeline(user: SocialNetworkUsers, start: int = 0, end: int = None, published=True, community_mode=False):
    """Get the timeline of the user. Assumes that the user is authenticated."""

    if community_mode:
        # T4
        # in community mode, posts of communities are displayed if ALL of the following criteria are met:
        # 1. the author of the post is a member of the community
        # 2. the user is a member of the community
        # 3. the post contains the community’s expertise area
        # 4. the post is published or the user is the author

        #pass
        #########################
        # add your code here
        #########################

        # T4 c
        posts = Posts.objects.none()                                 # create empty QuerySet
        communities_of_user = user.communities.all()                 # get all communities of the user

        for community in communities_of_user:                        # 2 -> "user is a member of the community" => iterate through only the users communities
            posts = posts| Posts.objects.filter(                     # add posts that follow all the criteria
                Q(author__communities = community) &                 # 1-> posts in which the author is in that same (current) community
                Q(expertise_area_and_truth_ratings = community) &    # 3 (Posts -> PostExpertiseAreasAndRatings -> expertise_area) = current cummunity
                ((Q(published= True)) | Q( author = user))           # 4 
                ).distinct().order_by("-submitted")                  # remove duplicates and order by newest post first              

    else:
        # in standard mode, posts of followed users are displayed
        _follows = user.follows.all()
        posts = Posts.objects.filter(
            (Q(author__in=_follows) & Q(published=published)) | Q(author=user)
        ).order_by("-submitted")
    if end is None:
        return posts[start:]
    else:
        return posts[start:end+1]


def search(keyword: str, start: int = 0, end: int = None, published=True):
    """Search for all posts in the system containing the keyword. Assumes that all posts are public"""
    posts = Posts.objects.filter(
        Q(content__icontains=keyword)
        | Q(author__email__icontains=keyword)
        | Q(author__first_name__icontains=keyword)
        | Q(author__last_name__icontains=keyword),
        published=published,
    ).order_by("-submitted")
    if end is None:
        return posts[start:]
    else:
        return posts[start:end+1]


def follows(user: SocialNetworkUsers, start: int = 0, end: int = None):
    """Get the users followed by this user. Assumes that the user is authenticated."""
    _follows = user.follows.all()
    if end is None:
        return _follows[start:]
    else:
        return _follows[start:end+1]


def followers(user: SocialNetworkUsers, start: int = 0, end: int = None):
    """Get the followers of this user. Assumes that the user is authenticated."""
    _followers = user.followed_by.all()
    if end is None:
        return _followers[start:]
    else:
        return _followers[start:end+1]


def follow(user: SocialNetworkUsers, user_to_follow: SocialNetworkUsers):
    """Follow a user. Assumes that the user is authenticated. If user already follows the user, signal that."""
    if user_to_follow in user.follows.all():
        return {"followed": False}
    user.follows.add(user_to_follow)
    user.save()
    return {"followed": True}


def unfollow(user: SocialNetworkUsers, user_to_unfollow: SocialNetworkUsers):
    """Unfollow a user. Assumes that the user is authenticated. If user does not follow the user anyway, signal that."""
    if user_to_unfollow not in user.follows.all():
        return {"unfollowed": False}
    user.follows.remove(user_to_unfollow)
    user.save()
    return {"unfollowed": True}


def submit_post(
    user: SocialNetworkUsers,
    content: str,
    cites: Posts = None,
    replies_to: Posts = None,
):
    """Submit a post for publication. Assumes that the user is authenticated.
    returns a tuple of three elements:
    1. a dictionary with the keys "published" and "id" (the id of the post)
    2. a list of dictionaries containing the expertise areas and their truth ratings
    3. a boolean indicating whether the user was banned and logged out and should be redirected to the login page
    """

    # create post  instance:
    post = Posts.objects.create(
        content=content,
        author=user,
        cites=cites,
        replies_to=replies_to,
    )

    # classify the content into expertise areas:
    # only publish the post if none of the expertise areas contains bullshit:
    _at_least_one_expertise_area_contains_bullshit, _expertise_areas = (
        post.determine_expertise_areas_and_truth_ratings()
    )
    post.published = not _at_least_one_expertise_area_contains_bullshit

    redirect_to_logout = False

    # T1:
    # A post must not be published if the author already has negative fame
    # in at least one expertise area assigned to this post.
    # This rule is independent of the truth rating of the new post.
    for expertise_area_and_rating in _expertise_areas:
        expertise_area = expertise_area_and_rating["expertise_area"]

        # Check whether the current user has a fame entry for this expertise area
        # and whether that fame level is negative.
        user_has_negative_fame_in_area = Fame.objects.filter(
            user=user,
            expertise_area=expertise_area,
            fame_level__numeric_value__lt=0,
        ).exists()

        # If the user has negative fame in this expertise area,
        # the post is recorded in the database, but it must not be published.
        if user_has_negative_fame_in_area:
            post.published = False
            break

    # T2:
    # If the post has a negative truth rating in an expertise area,
    # the author's fame profile must be adjusted for exactly that expertise area.
    for expertise_area_and_rating in _expertise_areas:
        expertise_area = expertise_area_and_rating["expertise_area"]
        truth_rating = expertise_area_and_rating["truth_rating"]

        # Only negative truth ratings influence the fame profile.
        # If there is no truth rating or the truth rating is non-negative,
        # nothing has to be changed for this expertise area.
        if truth_rating is None or truth_rating.numeric_value >= 0:
            continue

        try:
            # T2a:
            # Try to find an existing fame entry for this user and expertise area.
            fame_entry = Fame.objects.get(
                user=user,
                expertise_area=expertise_area,
            )

            try:
                # If the fame entry exists, lower it to the next lower fame level.
                # The method get_next_lower_fame_level() is defined in FameLevels.
                fame_entry.fame_level = fame_entry.fame_level.get_next_lower_fame_level()
                fame_entry.save()

                # T4 d 
                # if the fame level is below Super Pro (=100) -> remove from community 
                if fame_entry.fame_level.numeric_value < 100:
                    user.communities.remove(expertise_area)

            except ValueError:
                # T2c:
                # If there is no lower fame level anymore, the user must be banned.
                # In this case, the old fame level remains unchanged.
                user.is_active = False
                user.is_banned = True
                user.save()

                # All posts of this user must be unpublished,
                # but they must stay in the database.
                Posts.objects.filter(author=user).update(published=False)

                # The newly submitted post is also unpublished.
                post.published = False

                # Signal to the view that the user should be logged out
                # and redirected to the login page.
                redirect_to_logout = True

                # Once the user is banned, we do not need to process more areas.
                break

        except Fame.DoesNotExist:
            # T2b:
            # If the user has no fame entry for this expertise area yet,
            # create a new negative fame entry with fame level "Confuser".
            confuser_level = FameLevels.objects.get(name="Confuser")

            Fame.objects.create(
                user=user,
                expertise_area=expertise_area,
                fame_level=confuser_level,
            )

            # T4 d
            # if the fame level is below Super Pro (=100) -> remove from community 

            # if confuser_level.numeric_value <100: 
            # -> not needed because "Confuser" has an level of -10 <100

            # user.communities.remove(expertise_area) 
            # -> not needed because T7 checks wether you have a minimum fame level of 100 before joining a community
            # (because there is no fame entry this user cant be in a community)


    post.save()

    return (
        {"published": post.published, "id": post.id},
        _expertise_areas,
        redirect_to_logout,
    )


def rate_post(
    user: SocialNetworkUsers, post: Posts, rating_type: str, rating_score: int
):
    """Rate a post. Assumes that the user is authenticated. If user already rated the post with the given rating_type,
    update that rating score."""
    user_rating = None
    try:
        user_rating = user.userratings_set.get(post=post, rating_type=rating_type)
    except user.userratings_set.model.DoesNotExist:
        pass

    if user == post.author:
        raise PermissionError(
            "User is the author of the post. You cannot rate your own post."
        )

    if user_rating is not None:
        # update the existing rating:
        user_rating.rating_score = rating_score
        user_rating.save()
        return {"rated": True, "type": "update"}
    else:
        # create a new rating:
        user.userratings_set.add(
            post,
            through_defaults={"rating_type": rating_type, "rating_score": rating_score},
        )
        user.save()
        return {"rated": True, "type": "new"}


def fame(user: SocialNetworkUsers):
    """Get the fame of a user. Assumes that the user is authenticated."""
    try:
        user = SocialNetworkUsers.objects.get(id=user.id)
    except SocialNetworkUsers.DoesNotExist:
        raise ValueError("User does not exist")

    return user, Fame.objects.filter(user=user)


def bullshitters():
    """Return a Python dictionary mapping each existing expertise area in the fame profiles to a list of the users
    having negative fame for that expertise area. Each list should contain Python dictionaries as entries with keys
    ``user'' (for the user) and ``fame_level_numeric'' (for the corresponding fame value), and should be ranked, i.e.,
    users with the lowest fame are shown first, in case there is a tie, within that tie sort by date_joined
    (most recent first). Note that expertise areas with no expert may be omitted.
    """
    #pass
    #########################
    # add your code here
    #########################


    """ expertise_area -> ( list of users having negative fame (list contains dictionaries with users -> user , fame_level_numeric-> corresponding value) )"""

    #T3
    erg = {}

    # filter users having a negative fame for that expertise area and order by those vlaues (asc)
    neg_fame_entries = Fame.objects.filter(fame_level__numeric_value__lt =  0).order_by("fame_level__numeric_value" , "-user__date_joined")

    # "expertise areas with no bullshitters may be omitted" -> iterate only through negative entries
    for x in neg_fame_entries: 
        if x.expertise_area not in erg:
                
                # add new key with that expertise_area and add an empty list for the values (users)
                erg[x.expertise_area] = []
        
        # for key=expertise_area add the values to the list 
        erg[x.expertise_area].append(
            {
                "user": x.user,
                "fame_level_numeric" : x.fame_level.numeric_value 
            }
        )
    return erg 
        






def join_community(user: SocialNetworkUsers, community: ExpertiseAreas):
    """Join a specified community. Note that this method does not check whether the user is eligible for joining the
    community.
    """
    #pass
    #########################
    # add your code here
    #########################

    # T4 b
    user.communities.add(community)     
    user.save()





def leave_community(user: SocialNetworkUsers, community: ExpertiseAreas):
    """Leave a specified community."""
    #pass
    #########################
    # add your code here
    #########################

    # T4 b
    user.communities.remove(community)     
    user.save()



def similar_users(user: SocialNetworkUsers):
    """Compute the similarity of user with all other users. The method returns a QuerySet of FameUsers annotated
    with an additional field 'similarity'. Sort the result in descending order according to 'similarity', in case
    there is a tie, within that tie sort by date_joined (most recent first)"""

    # T5 
    
    own_fame_entries = Fame.objects.filter(user=user).select_related(
        "expertise_area",
        "fame_level",
    )

    number_of_own_expertise_areas = own_fame_entries.count()

    if number_of_own_expertise_areas == 0:
        return FameUsers.objects.none()

    similar_user_scores = []

    for other_user in FameUsers.objects.exclude(id=user.id):
        matching_expertise_areas = 0

        for own_fame_entry in own_fame_entries:
            other_fame_entry = Fame.objects.filter(
                user=other_user,
                expertise_area=own_fame_entry.expertise_area,
            ).select_related("fame_level").first()

            if other_fame_entry is None:
                continue

            fame_difference = abs(
                own_fame_entry.fame_level.numeric_value
                - other_fame_entry.fame_level.numeric_value
            )

            if fame_difference <= 100:
                matching_expertise_areas += 1

        similarity = matching_expertise_areas / number_of_own_expertise_areas

        if similarity > 0:
            similar_user_scores.append(
                (other_user.id, similarity, other_user.date_joined)
            )

    similar_user_scores.sort(
        key=lambda entry: (entry[1], entry[2]),
        reverse=True
    )

    sorted_user_ids = [entry[0] for entry in similar_user_scores]

    if not sorted_user_ids:
        return FameUsers.objects.none()

    similarity_annotation = Case(
        *[
            When(id=user_id, then=Value(similarity))
            for user_id, similarity, _date_joined in similar_user_scores
        ],
        output_field=FloatField(),
    )

    ordering_annotation = Case(
        *[
            When(id=user_id, then=Value(position))
            for position, user_id in enumerate(sorted_user_ids)
        ],
        output_field=IntegerField(),
    )

    return (
        FameUsers.objects
        .filter(id__in=sorted_user_ids)
        .annotate(
            similarity=similarity_annotation,
            similarity_order=ordering_annotation,
        )
        .order_by("similarity_order")
    )
