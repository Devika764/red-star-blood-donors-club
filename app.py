import re
import uuid
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
from werkzeug.utils import secure_filename

load_dotenv()

instance_path = "/tmp" if os.getenv("VERCEL") else os.path.join(os.getcwd(), "instance")
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
    try:
        from PIL import Image, ImageOps
    except ImportError:
        Image = None

    saved = []

    folder = app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)

    print("UPLOAD FOLDER:", os.path.abspath(folder))
    print("FILES RECEIVED:", len(files))

    for f in files:
        if not f or not f.filename:
            print("SKIPPED: No filename")
            continue

        print("PROCESSING:", f.filename)

        ext = os.path.splitext(secure_filename(f.filename))[1].lower()

        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            print("SKIPPED: Unsupported extension:", ext)
            continue

        name = uuid.uuid4().hex[:12]

        if Image:
            try:
                img = ImageOps.exif_transpose(Image.open(f.stream))
                img.thumbnail((1600, 1600))
                img = img.convert("RGB")

                name += ".jpg"
                output_path = os.path.join(folder, name)

                img.save(
                    output_path,
                    "JPEG",
                    quality=82,
                    optimize=True
                )

                print("SAVED:", output_path)

            except Exception as e:
                print("IMAGE ERROR:", repr(e))
                continue

        else:
            name += ext
            output_path = os.path.join(folder, name)

            try:
                f.save(output_path)
                print("SAVED:", output_path)
            except Exception as e:
                print("FILE SAVE ERROR:", repr(e))
                continue

        saved.append(name)

    print("TOTAL SAVED:", saved)

    return saved

@app.route("/admin/donation/add", methods=["GET", "POST"])
@login_required
def add_donation():
    if request.method == "POST":
        saved = save_photos(request.files.getlist("photos"))

        donation = DonationUpdate(
            donor_name=request.form["donor_name"].strip(),
            blood_group=request.form.get("blood_group", "").strip(),
            phone=request.form.get("phone", "").strip(),
            location=request.form["location"].strip(),
            donation_date=request.form["donation_date"],
            photo=saved[0] if saved else None,
            photos=",".join(saved) if saved else None,
            description=request.form.get("description"),
            video_url=request.form.get("video_url", "").strip() or None
        )

        db.session.add(donation)
        db.session.commit()

        return redirect(url_for("admin_dashboard"))

    return render_template("add_donation.html")
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
    donors = Donor.query.order_by(Donor.id.desc()).all()
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
    if request.method == "POST":
        saved = save_photos(request.files.getlist("photos"))
        caption = request.form.get("caption", "").strip() or None
        for name in saved:
            db.session.add(Photo(filename=name, caption=caption))
        db.session.commit()
        return redirect(url_for("admin_gallery"))

    photos = Photo.query.order_by(Photo.id.desc()).all()
    return render_template("admin_gallery.html", photos=photos)


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









