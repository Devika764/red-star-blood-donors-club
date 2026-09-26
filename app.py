import re
import uuid
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader

load_dotenv(override=True)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

instance_path = "/tmp" if os.name != "nt" else os.path.abspath("instance")
app = Flask(__name__, instance_path=instance_path)

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///blood_donation.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin_login"


class Donor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    blood_group = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    last_donation_date = db.Column(db.String(20))


class DonationUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_name = db.Column(db.String(100), nullable=False)
    blood_group = db.Column(db.String(10), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    donation_date = db.Column(db.String(20), nullable=False)
    photo = db.Column(db.String(255))
    description = db.Column(db.Text)
    photos = db.Column(db.Text)
    video_url = db.Column(db.String(500))


class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(200))


class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))


with app.app_context():
    db.create_all()

    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if admin_username and admin_password:
        existing_admin = Admin.query.filter_by(username=admin_username).first()

        if not existing_admin:
            new_admin = Admin(
                username=admin_username,
                password_hash=generate_password_hash(admin_password)
            )
            db.session.add(new_admin)
            db.session.commit()


@app.route("/")
def home():
    donation_updates = DonationUpdate.query.order_by(
        DonationUpdate.id.desc()
    ).all()

    gallery_photos = Photo.query.order_by(Photo.id.desc()).all()

    return render_template(
        "index.html",
        donation_updates=donation_updates,
        gallery_photos=gallery_photos
    )


@app.route("/donate", methods=["GET", "POST"])
def donate():
    if request.method == "POST":
        donor = Donor(
            name=request.form["name"],
            blood_group=request.form["blood_group"],
            phone=request.form["phone"],
            location=request.form["location"],
            last_donation_date=request.form.get("last_donation_date")
        )

        db.session.add(donor)
        db.session.commit()

        return render_template("donate_success.html", donor_name=donor.name)

    return render_template("donate.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")



@app.route("/admin/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        recovery_code = request.form.get("recovery_code", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        admin = Admin.query.filter_by(username=username).first()

        expected_code = os.getenv("ADMIN_RECOVERY_CODE", "").strip()

        if not admin or not expected_code or recovery_code != expected_code:
            return render_template(
                "forgot_password.html",
                error="Invalid username or recovery code."
            )

        if len(new_password) < 8:
            return render_template(
                "forgot_password.html",
                error="New password must be at least 8 characters."
            )

        if new_password != confirm_password:
            return render_template(
                "forgot_password.html",
                error="New passwords do not match."
            )

        admin.password_hash = generate_password_hash(new_password)
        db.session.commit()

        return redirect(url_for("admin_login", reset="success"))

    return render_template("forgot_password.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        admin = Admin.query.filter_by(username=username).first()

        if admin and check_password_hash(
            admin.password_hash,
            password
        ):
            login_user(admin)
            next_url = request.args.get("next", "")
            if next_url.startswith("/admin"):
                return redirect(next_url)
            return redirect(url_for("admin_dashboard"))

        return render_template(
            "admin_login.html",
            error="Invalid username or password.",
            donors=Donor.query.order_by(Donor.id.desc()).all()
        )

    return render_template(
        "admin_login.html",
        donors=Donor.query.order_by(Donor.id.desc()).all()
    )




@app.route("/admin/donation/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_donation(id):

    donation = db.session.get(DonationUpdate, id)

    if not donation:
        return "Donation not found", 404

    if request.method == "POST":

        donation.donor_name = request.form["donor_name"]
        donation.blood_group = request.form["blood_group"]
        donation.phone = request.form["phone"]
        donation.location = request.form["location"]
        donation.donation_date = request.form["donation_date"]
        donation.description = request.form.get("description")

        photo = request.files.get("photo")

        if photo and photo.filename:

            if donation.photo:

                old_photo = os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    donation.photo
                )

                if os.path.exists(old_photo):
                    os.remove(old_photo)

            photo_filename = secure_filename(photo.filename)

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    photo_filename
                )
            )

            donation.photo = photo_filename

        db.session.commit()

        return redirect(url_for("admin_dashboard"))

    return render_template(
        "edit_donation.html",
        donation=donation
    )
def youtube_embed(url):
    if not url:
        return None
    m = (
        re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
        or re.search(r"youtube\.com/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})", url)
        or re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    )
    return f"https://www.youtube.com/embed/{m.group(1)}" if m else None


app.add_template_filter(youtube_embed, "yt_embed")


def save_photos(files):
    saved = []
    print("========== PHOTO UPLOAD START ==========")
    print("FILES RECEIVED:", len(files))

    for f in files:
        if not f or not f.filename:
            print("SKIPPED: Empty file")
            continue

        filename = secure_filename(f.filename)
        ext = os.path.splitext(filename)[1].lower()

        print("PROCESSING:", filename)

        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            print("SKIPPED: Unsupported image type")
            continue

        try:
            file_data = f.read()

            if not file_data:
                print("SKIPPED: File is empty")
                continue

            result = cloudinary.uploader.upload(
                file_data,
                folder="red-star-blood-donors-club/activities",
                resource_type="image"
            )

            image_url = result.get("secure_url")

            if image_url:
                saved.append(image_url)
                print("CLOUDINARY SAVED:", image_url)
            else:
                print("CLOUDINARY ERROR: No secure URL")

        except Exception as e:
            print("PHOTO UPLOAD ERROR:", repr(e))
            raise

    print("TOTAL SAVED:", len(saved))
    print("========== PHOTO UPLOAD END ==========")
    return saved
@app.route("/admin/logout")
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    donors = Donor.query.order_by(
        Donor.id.desc()
    ).all()

    donation_updates = DonationUpdate.query.order_by(
        DonationUpdate.id.desc()
    ).all()

    return render_template(
        "admin_dashboard.html",
        donors=donors,
        donation_updates=donation_updates
    )



@app.route("/admin/donors")
@login_required
def admin_donors():
    donors = Donor.query.order_by(Donor.id.asc()).all()
    return render_template("admin_donors.html", donors=donors)

@app.route("/admin/donors/edit/<int:id>", methods=["GET", "POST"])
@login_required
def admin_edit_donor(id):
    donor = Donor.query.get_or_404(id)

    if request.method == "POST":
        donor.name = request.form["name"]
        donor.blood_group = request.form["blood_group"]
        donor.phone = request.form["phone"]
        donor.location = request.form["location"]
        donor.last_donation_date = request.form.get("last_donation_date")

        db.session.commit()

        return redirect(url_for("admin_donors"))

    return render_template("admin_edit_donor.html", donor=donor)
@app.route("/admin/donors/delete/<int:id>", methods=["POST"])
@login_required
def admin_delete_donor(id):
    donor = Donor.query.get_or_404(id)
    db.session.delete(donor)
    db.session.commit()
    return redirect(url_for("admin_donors"))

@app.route("/admin/donation/delete/<int:id>")
@login_required
def delete_donation(id):

    donation = db.session.get(DonationUpdate, id)

    if not donation:
        return "Donation not found", 404

    if donation.photo:
        photo_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            donation.photo
        )

        if os.path.exists(photo_path):
            os.remove(photo_path)

    db.session.delete(donation)
    db.session.commit()

    return redirect(url_for("admin_dashboard"))

@app.route("/admin/gallery", methods=["GET", "POST"])
@login_required
def admin_gallery():
    debug_msg = None
    if request.method == "POST":
        files = request.files.getlist("photos")
        debug_msg = f"Files received: {len(files)} | Names: {[f.filename for f in files]}"
        try:
            saved = save_photos(files)
            debug_msg += f" | Saved URLs: {saved}"
            caption = request.form.get("caption", "").strip() or None
            for name in saved:
                db.session.add(Photo(filename=name, caption=caption))
            db.session.commit()
            debug_msg += " | DB commit OK"
        except Exception as e:
            debug_msg += f" | ERROR: {str(e)}"

    photos = Photo.query.order_by(Photo.id.desc()).all()
    return render_template("admin_gallery.html", photos=photos, debug_msg=debug_msg)


@app.route("/admin/gallery/edit/<int:id>", methods=["POST"])
@login_required
def admin_edit_photo(id):
    photo = Photo.query.get_or_404(id)
    photo.caption = request.form.get("caption", "").strip() or None
    db.session.commit()
    return redirect(url_for("admin_gallery"))


@app.route("/admin/gallery/delete/<int:id>", methods=["POST"])
@login_required
def admin_delete_photo(id):
    photo = Photo.query.get_or_404(id)
    path = os.path.join(app.config["UPLOAD_FOLDER"], photo.filename)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(photo)
    db.session.commit()
    return redirect(url_for("admin_gallery"))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)















