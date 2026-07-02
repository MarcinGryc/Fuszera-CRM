@distribution_bp.route("/distribution", methods=["GET", "POST"])
@login_required
def distribution():
    if request.method == "POST":
        contact = DistributionContact(
            list_type=request.form.get("list_type"),
            email=request.form.get("email"),
        )

        db.session.add(contact)
        db.session.commit()
        return redirect(url_for("distribution.distribution"))

    b2b = DistributionContact.query.filter_by(list_type="b2b").order_by(DistributionContact.email).all()
    individual = DistributionContact.query.filter_by(list_type="individual").order_by(DistributionContact.email).all()

    return render_template("distribution.html", b2b=b2b, individual=individual)