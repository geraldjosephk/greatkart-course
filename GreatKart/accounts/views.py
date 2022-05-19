from GreatKart.orders.models import OrderProduct
from orders.models import Order, OrderProduct
from django.shortcuts import render, redirect, get_object_or_404
from .forms import RegistrationForm, UserForm, UserProfileForm
from .models import Account, UserProfile
from django.contrib import messages, auth
from django.contrib.auth.decorators import login_required

# from django.http import HttpResponse

# Email Verification
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage

from carts.views import _cart_id
from carts.models import Cart, CartItem

import requests

# Create your views here.
def register(request):
    """
    Function to register new users after verification.
    Validates user data submitted in registration form, creates user in database and saves.
    Sends an encoded activation token to user email.
    """
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # store data according to field type
            first_name = form.cleaned_data["first_name"]
            last_name = form.cleaned_data["last_name"]
            email = form.cleaned_data["email"]
            phone_number = form.cleaned_data["phone_number"]
            password = form.cleaned_data["password"]
            # split email address to show first letters before the @ and assign as username
            username = email.split("@")[0]

            user = Account.objects.create_user(
                first_name=first_name,
                last_name=last_name,
                email=email,
                username=username,
                password=password,
            )
            user.phone_number = phone_number
            user.save()

            # User authentication
            current_site = get_current_site(request)
            mail_subject = "Please activate your account."
            message = render_to_string(
                "accounts/account_verification_email.html",
                {
                    "user": user,
                    "domain": current_site,
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                },
            )
            to_email = email
            send_email = EmailMessage(mail_subject, message, to=[to_email])
            send_email.send()

            return redirect("/accounts/login/?command=verification&email=" + email)
    else:
        form = RegistrationForm()

    context = {
        "form": form,
    }
    return render(request, "accounts/register.html", context)


def login(request):
    """
    Function to login user and redirect them to the home page.
    Accepts email and password post requests. Matches email and
    passwords to users in database. If user exists in database,
    login and redirect to home page. Otherwise, user prompted to login again
    """
    if request.method == "POST":
        email = request.POST.get("email")  # get email input posted
        password = request.POST.get("password")

        user = auth.authenticate(
            email=email, password=password
        )  # check if email and password is active
        if user is not None:
            try:
                cart = Cart.objects.get(cart_id=_cart_id(request))
                is_cart_item_exists = CartItem.objects.filter(cart=cart).exists()

                if is_cart_item_exists:
                    cart_item = CartItem.objects.filter(cart=cart)

                    # Getting product variations by cart id
                    product_variation = []
                    for item in cart_item:
                        variation = item.variations.all()
                        product_variation.append(list(variation))

                    cart_item = CartItem.objects.filter(user=user)
                    # fetch existing variations in database
                    # display current product variation
                    # fetch item id in database
                    existing_variations_list = []
                    id = []
                    for item in cart_item:
                        existing_variation = item.variations.all()
                        existing_variations_list.append(list(existing_variation))
                        id.append(item.id)
                    # Matching product_variations = [1,2,3,4,5,6] with existing_variations_list =[4,6]
                    for pr in product_variation:
                        if pr in existing_variations_list:
                            index = existing_variations_list.index(pr)
                            item_id = id[index]
                            item = CartItem.objects.get(id=item_id)
                            item.quantity += 1
                            item.user = user
                            item.save()
                        else:
                            cart_item = CartItem.objects.filter(cart=cart)
                            for item in cart_item:
                                item.user = user
                                item.save()
            except:
                pass

            auth.login(request, user)
            messages.success(request, "You are now logged in.")
            # dynamic page redirect
            url = request.META.get("HTTP_REFERER")
            try:
                query = requests.utils.urlparse(url).query
                # next=/cart/checkout/
                params = dict(x.split("=") for x in query.split("&"))
                if "next" in params:
                    nextPage = params["next"]
                    return redirect(nextPage)
                return redirect("dashboard")  # redirect to home page
            except:
                return redirect("dashboard")  # redirect to home page
        else:
            messages.error(request, "Invalid Login credentials.")
            return redirect("login")
    return render(request, "accounts/login.html")


# to logout, user must be already login
@login_required(login_url="login")
def logout(request):
    """
    Function to logout user and redirect them to login page.
    The user must be already logged in
    """
    auth.logout(request)
    messages.success(request, "You are logged out.")
    return redirect("login")


def activate(request, uidb64, token):
    """
    Function flags user account to active.
    Accepts user request,uidb64 and user token as arguments.
    Decodes the user token and matches uid with primary key.
    If user does not activate the token, the user account is not activated.
    Otherwise, user account is activated as 'is_active' in Django Admin.
    The user is redirected to the login page.
    If user takes long to use the token, or uses an expired authemtication token,
    the user is redirected to the register page.
    """
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = Account._default_manager.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, "Congratulations! Your account is activated.")
        return redirect("login")

    else:
        messages.error(request, "Invalid activation link.")
        return redirect("register")


@login_required(login_url="login")
def dashboard(request):
    """
    Function to display user dashboard.
    The user must be logged in.
    """
    orders = Order.objects.order_by("-created_at").filter(
        user_id=request.user.id, is_ordered=True
    )
    orders_count = orders.count()
    context = {
        "orders_count": orders_count,
    }
    return render(request, "accounts/dashboard.html", context)


def forgotPassword(request):
    """
    Function assists the user to reset passord.
    Accepts email form user for validation.
    if the email exists in the database, a reset
    password authentication email is sent to the valid email address.
    Otherwise, the user is redirected to forgot password page
    """
    if request.method == "POST":
        email = request.POST.get("email")
        if Account.objects.filter(email=email).exists():
            user = Account.objects.get(email__exact=email)

            # Reset password email
            current_site = get_current_site(request)
            mail_subject = "Reset your password."
            message = render_to_string(
                "accounts/reset_password_email.html",
                {
                    "user": user,
                    "domain": current_site,
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                },
            )
            to_email = email
            send_email = EmailMessage(mail_subject, message, to=[to_email])
            send_email.send()

            messages.success(
                request, "Password reset email has been sent to your email address."
            )
            return redirect("login")

        else:
            messages.error(request, "Account does not exist!")
            return redirect("forgotPassword")

    return render(request, "accounts/forgotPassword.html")


def resetpassword_validate(request, uidb64, token):
    """
    Function validates password change for user.
    Accepts user uidb64 and token as arguments.
    Decodes the user token and matches uid with primary key.
    If user does not activate the token, the user account is not activated.
    Otherwise, user session id is recordes and redirected to the reset password page.
    If user takes long to use the token, or uses an expired authentication token,
    the user is redirected to the login page.
    """
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = Account._default_manager.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        request.session["uid"] = uid
        messages.success(request, "Please reset your password")
        return redirect("resetPassword")

    else:
        messages.error(request, "This link is expired!")
        return redirect("login")


def resetPassword(request):
    if request.method == "POST":
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password == confirm_password:
            uid = request.session.get("uid")
            user = Account.objects.get(pk=uid)
            user.set_password(password)
            user.save()
            messages.success(request, "Password reset successful.")
            return redirect("login")
        else:
            messages.error(request, "Passwords do not match!")
            return redirect("resetPassword")
    else:
        return render(request, "accounts/resetPassword.html")


@login_required(login_url="login")
def my_orders(request):
    orders = Order.objects.filter(user_id=request.user.id, is_ordered=True).order_by(
        "-created_at"
    )  # the hyphen is order in ascending order
    context = {
        "orders": orders,
    }
    return render(request, "accounts/my_orders.html", context)


@login_required(login_url="login")
def edit_profile(request):
    userprofile = get_object_or_404(UserProfile, user=request.user)
    if request.method == "POST":
        user_form = UserForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(
            request.POST, request.FILES, instance=userprofile
        )
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("edit_profile")
    else:
        user_form = UserForm(instance=request.user)
        profile_form = UserProfileForm(instance=userprofile)
    context = {
        "user_form": user_form,
        "profile_form": profile_form,
        "userprofile": userprofile,
    }
    return render(request, "accounts/edit_profile.html", context)


@login_required(login_url="login")
def change_password(request):
    if request.method == "POST":
        current_password = request.POST["current_password"]
        new_password = request.POST["new_password"]
        confirm_password = request.POST["confirm_password"]

        user = Account.objects.get(username__exact=request.user.username)

        if new_password == confirm_password:
            success = user.check_password(current_password)
            if success:
                user.set_password(new_password)
                user.save()
                messages.success(request, "Password updated successfully")
                return redirect("change_password")
            else:
                messages.error(request, "Please enter valid current password")
                return redirect("change_password")
        else:
            messages.error(request, "Passwords do not match!")
            return redirect("change_password")

    return render(request, "accounts/change_password.html")


@login_required(login_url="login")
def order_details(request, order_id):
    order_details = OrderProduct.objects.filter(
        order__order_number=order_id
    )  # Access foreignkey with double under score
    order = Order.objects.get(order_number=order_id)
    subtotal = 0
    for i in order_details:
        subtotal += i.product_price * i.quantity
    context = {
        "order_details": order_details,
        "order": order,
        "subtotal": subtotal,
    }

    return render(request, "accounts/order_details.html", context)
