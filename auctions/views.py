from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse

from .models import User, AuctionListing, AuctionBid,\
    AuctionWatchList, AuctionComment


def search_by_category(request, category):
    return index(request, category=category)


def index(request, watchlist=False, message=None, error=None, category=None):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    rows = list()

    # If category then get filtered results accordingly:
    if category:
        auctions = AuctionListing.objects.filter(
            closed=False, category=category)
    else:
        auctions = AuctionListing.objects.filter(
            closed=False)

    # Prepare data accordingly based on watchlist flag
    for auction in auctions:
        auction.watched = False

        # If the item is already watched, set watched=True
        if AuctionWatchList.objects.filter(
           auction=auction, user=request.user).exists():
            auction.watched = True
        # If watchlist is true and item in not watched, then ignore
        if watchlist and not auction.watched:
            continue

        auction.owner_item = False
        # If the item is created by logged in user, set owner_item flag True
        if auction.user == request.user:
            auction.owner_item = True

        # Add item to the rows
        rows.append(auction)

    # UI params
    params = {
        'rows': rows,
        'watchlist': watchlist,
        'message': message,
        'error': error
    }
    return render(
        request,
        "auctions/index.html",
        params
    )


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        # Check if authentication successful
        if user is not None:
            login(request, user)
            return index(request, message="Successfully logged in")
        else:
            return render(request, "auctions/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "auctions/login.html")


def logout_view(request):
    logout(request)
    message = "Successfully logged out."
    return index(request, message=message)


def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]
        description = request.POST["description"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "auctions/register.html", {
                "message": "Passwords must match."
            })

        # Attempt to create new user
        try:
            user = User.objects.create_user(
                username, email, password, description=description)
            user.save()
        except IntegrityError:
            return render(request, "auctions/register.html", {
                "message": "Username already taken."
            })
        login(request, user)
        message = "Successfully registered and logged in"
        return index(request, message=message)
    else:
        return render(request, "auctions/register.html")


def create_auction(request):
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    if request.method == "POST":

        # Read UI parameters
        title = request.POST["title"]
        description = request.POST["description"]
        starting_bid = request.POST["starting_bid"]
        url = request.POST["url"]
        category = request.POST["category"]

        # Check if bid is missing
        if not starting_bid:
            error = 'Bid value missing'
            return render(request, "auctions/create_auction.html",
                          {'error': error})

        # Create listing
        response = AuctionListing.objects.create(
            title=title,
            description=description,
            user=request.user,
            starting_bid=starting_bid,
            listing_url=url,
            category=category

        )
        # Return to home page
        message = "Successfully created listing."
        return index(request, message=message)

    else:
        return render(request, "auctions/create_auction.html")


def auction_detail(request, id):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Check listing availability
    if not AuctionListing.objects.filter(id=id).exists():
        return(HttpResponse("Requested Item doesn't exist"))
    item = AuctionListing.objects.get(id=id)

    # Get highest bid for this listing
    item_bid = AuctionBid.objects.filter(auction=item).order_by("-value")
    highest_bid = item_bid[0].value if item_bid else item.starting_bid

    # Read comments for this listing
    comments = AuctionComment.objects.filter(
        auction=item).order_by("created_at")

    # Check if bid is won (applicable for closed listing)
    bid_won_flag = None
    if item.closed:
        bid_won_flag = bid_won(item_bid[0], request.user)

    # Prepare params to feed into the details template
    params = {
        'item': item,
        'highest_bid': highest_bid,
        'comments': comments,
        'bid_won': bid_won_flag,
    }
    return render(
        request,
        "auctions/auction_detail.html",
        params)


def place_bid(request, id):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Check listing availability
    if not AuctionListing.objects.filter(id=id).exists():
        return HttpResponse("Requested Item doesn't exist")
    item = AuctionListing.objects.get(id=id)

    if request.method == "POST":
        # Read bid value from UI and convert to float
        bid_amount = request.POST["bid_amount"]
        try:
            bid_amount = float(bid_amount)
        except ValueError:
            error = "Invalid Bid Value."
            return index(request, error=error)

        # Read highest bid value on this item
        highest_bid = AuctionBid.objects.filter(
            auction=item).order_by("-value")
        highest_bid = highest_bid[0].value if highest_bid\
            else item.starting_bid

        # If supplied bid value is less than highest bid in the db
        if not bid_amount > highest_bid:
            error = "Bid value must be greater than {}".format(highest_bid)
            return index(request, error=error)

        # Create bid
        response = AuctionBid.objects.create(
            auction=item,
            user=request.user,
            value=bid_amount
        )
        # Return to home page
        message = "Successfully placed bid."
        return index(request, message=message)
    return render(request, "auctions/place_bid.html", {'item': item})


def watchlist(request):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Return to home page with watchlist flag True
    return index(request, watchlist=True)


def add_to_watchlist(request, id):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Check listing availability
    if not AuctionListing.objects.filter(id=id).exists():
        return HttpResponse("Requested Item doesn't exist")
    item = AuctionListing.objects.get(id=id)

    # Raise error if item is already in watchlist of loggedin user
    if AuctionWatchList.objects.filter(
       auction=item, user=request.user).exists():
        error = "Requested Item already in watchlist"
        return index(request, error=error, watchlist=True)

    # Add to watchlist
    response = AuctionWatchList.objects.create(
        auction=item,
        user=request.user,
    )

    # Return to home page
    message = "Successfully added to watchlist."
    return index(request, message=message, watchlist=True)


def remove_from_watchlist(request, id):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Check listing availability
    if not AuctionListing.objects.filter(id=id).exists():
        return HttpResponse("Requested Item doesn't exist")
    item = AuctionListing.objects.get(id=id)

    # Raise error if item is not in watchlist
    if not AuctionWatchList.objects.filter(
       auction=item, user=request.user).exists():
        error = "Requested Item not in watchlist"
        return index(request, error=error, watchlist=True)
    # Remove from watchlist
    item = AuctionWatchList.objects.get(auction=item, user=request.user)
    item.delete()

    # Return to home page
    message = "Successfully removed from watchlist."
    return index(request, message=message, watchlist=True)


def add_comment(request, id):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Check listing availability
    if not AuctionListing.objects.filter(id=id).exists():
        return HttpResponse("Requested Item doesn't exist")
    item = AuctionListing.objects.get(id=id)

    if request.method == "POST":
        # Read comment from UI
        comment = request.POST["comment"]

        # Add comment
        response = AuctionComment.objects.create(
            auction=item,
            user=request.user,
            comment=comment
        )
        # Return to home page
        message = "Successfully added a comment."
        return index(request, message=message)
    return render(request, "auctions/add_comment.html", {'item': item})


def close_auction(request, id):
    # Check login status
    if not request.user.is_authenticated:
        return render(request, "auctions/login.html", {
                "message": "User not logged in."
            })
    # Check listing availability
    if not AuctionListing.objects.filter(id=id, user=request.user).exists():
        return HttpResponse("Requested Item doesn't exist")
    item = AuctionListing.objects.get(id=id, user=request.user)

    # Update item and save
    item.closed = True
    item.save()

    # Return to home page
    message = "Successfully closed the listing."
    return index(request, message=message)


def available_categories(request):
    categories = AuctionListing.objects.order_by(
        'category').values('category').distinct()
    return render(request, "auctions/categories.html",
                  {'rows': categories})


def bid_won(item_bid, session_user):
    """
    If session_user and the bid user is same, bid is won by this user
    """
    if not item_bid.user == session_user:
        return
    return True
