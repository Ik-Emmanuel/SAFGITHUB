from application import app
from application.route_logic import SRMS
import datetime
from application import db
from flask import render_template, request, json, jsonify, Response, redirect, flash, url_for, session
from application.forms import LoginForm, RegisterForm
from application.models import User

global SRMS
SRMS = SRMS()


@app.route('/')
def login():
    if 'email' in session:
        return redirect(url_for('index'))

    return render_template('login2.html')


@app.route('/loginny', methods=['GET', 'POST'])
def loginny():
    try:
        form = LoginForm()

        if 'email' in session:
            return redirect(url_for('index'))

        if request.method == 'POST':
            valid = form.validate()

            if valid[0]:

                is_admin = valid[1]
                is_approved = valid[2]
                name = valid[3]
                is_super_admin = valid[4]
                email = form.email.data

                if is_approved:
                    if is_admin:
                        session['email'] = email
                        session['name'] = name
                        session['is_admin'] = is_admin
                        session['is_super_admin'] = is_super_admin

                        table = "[dbo].[SAF_users_activity_table]"

                        data = {
                            "Email": email,
                            "[Time-in]": str(datetime.datetime.now())
                        }

                        # print(f"data: {data}")

                        ins_qry = "SET QUOTED_IDENTIFIER OFF\
                                                       SET ANSI_NULLS ON \
                                                       INSERT INTO {tablename} ({columns}) VALUES {values};".format(
                            tablename=table,
                            columns=', '.join(data.keys()),
                            values=tuple(data.values())
                        )

                        try:
                            db.session.execute(ins_qry)
                            db.session.commit()
                        except Exception as e:
                            print(str(e))
                        # return redirect(url_for('index', user=name, admin=is_admin, super_admin=is_super_admin))
                        return redirect(url_for('index'))

                    else:
                        session['email'] = email
                        session['name'] = name
                        session['is_admin'] = is_admin
                        session['is_super_admin'] = is_super_admin

                        table = "[dbo].[SAF_users_activity_table]"

                        data = {
                            "Email": email,
                            "[Time-in]": str(datetime.datetime.now())
                        }

                        # print(f"data: {data}")

                        ins_qry = "SET QUOTED_IDENTIFIER OFF\
                                                                           SET ANSI_NULLS ON \
                                                                           INSERT INTO {tablename} ({columns}) VALUES {values};".format(
                            tablename=table,
                            columns=', '.join(data.keys()),
                            values=tuple(data.values())
                        )

                        try:
                            db.session.execute(ins_qry)
                            db.session.commit()
                        except Exception as e:
                            print(str(e))
                        # return redirect(url_for('index', user=name, admin=is_admin, super_admin=is_super_admin))
                        return redirect(url_for('index'))
                else:

                    flash("Your Signup request hasn't been approved. Kindly Contact site admin for approval", "danger")

                    return render_template('login2.html', form=form)
            else:

                flash("Wrong email or password. Please confirm your login details and try again", "danger")

                return render_template('login2.html', form=form)
        else:
            return render_template('login2.html', form=form)
    except Exception as e:
        print(str(e))
        flash("Something went wrong, please try to login again", "danger")

        return render_template('login2.html', form=form)


@app.route('/signout')
def signout():
    if 'email' not in session:
        return redirect(url_for('login'))

    email = session['email']
    session.pop('email', None)
    session.pop('name', None)
    session.pop('is_admin', None)
    session.pop('is_super_admin', None)

    table = "[dbo].[SAF_users_activity_table]"
    ins_qry = f"select top(1) [activity_id] from {table} where Email = '{email}' order by [Time-in] desc"

    try:
        result = db.session.execute(ins_qry)
        for row in result:
            activity_id = row[0]

        qry = f"update {table} set [Time-out] = '{str(datetime.datetime.now())}' where [activity_id] = {int(activity_id)}"

        db.session.execute(qry)
        db.session.commit()

    except Exception as e:
        print(str(e))

    return redirect(url_for('login'))


@app.route("/signup", methods=['POST', 'GET'])
def signup():
    form = RegisterForm()

    if request.method == 'POST':
        # and form.validate():
        email = form.email.data
        password = form.password.data
        # password_confirm = form.password_confirm.data

        first_name = form.first_name.data
        last_name = form.last_name.data
        is_admin = 0
        is_approved = 0
        is_super_admin = 0
        DateLoaded = str(datetime.datetime.now())
        valid = form.validate_email(email)

        if valid[0]:

            user = User(email=email, password=password, firstname=first_name, lastname=last_name, is_admin=is_admin,
                        is_super_admin=is_super_admin, is_approved=is_approved, DateLoaded=DateLoaded)
            db.session.add(user)
            db.session.commit()

            full_name = f"{first_name} {last_name}"

            # session['full_name'] = full_name

            SRMS.need = None
            SRMS.message = None

            # email = "moses.ikeakhe@sterling.ng"

            SRMS.task = "Signup_Team"
            SRMS.SendMail(full_name, email)

            SRMS.task = "Signup_User"
            SRMS.SendMail(full_name, email)

            flash(f"Hi {first_name}, your signup request has been successfully submitted for approval!", "success")

            return render_template("login2.html")
        else:

            flash(valid[1], "danger")

            return render_template("login2.html", form=form, title="Register New User")

    return render_template("login2.html", form=form, title="Register New User")


@app.route('/signuprequest', methods=["GET", "POST"])
def signuprequest():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))

    data = db.session.execute(
        "select user_id, firstname, Email, lastname, DateLoaded from dbo.SAF_users_table where is_Approved = 0 order by DateLoaded desc")
    result = []

    for data in db.session.query(User).instances(data):
        value = {
            "user_id": data.user_id,
            "Name": f"{data.firstname} {data.lastname}",
            "DateLoaded": data.DateLoaded,
            "Email": data.email
        }

        result.append(value)

    # data = user.query.filter_by(is_Approved=0).order_by(User.DateLoaded).all()
    # print(f"data: {result}")

    return render_template('request.html', user=session['email'], data=result)


@app.route('/adminrequest', methods=["GET", "POST"])
def adminrequest():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))

    data = db.session.execute(
        "select user_id, firstname, Email, lastname, DateLoaded from dbo.SAF_users_table where is_Admin = 0 order by DateLoaded desc")
    result = []

    for data in db.session.query(User).instances(data):
        value = {
            "user_id": data.user_id,
            "Name": f"{data.firstname} {data.lastname}",
            "DateLoaded": data.DateLoaded,
            "Email": data.email
        }

        result.append(value)

    # data = user.query.filter_by(is_Approved=0).order_by(User.DateLoaded).all()
    # print(f"data: {result}")

    return render_template('adminrequest.html', user=session['email'], data=result)


@app.route('/approverequest', methods=["GET"])
def approverequest():
    if 'email' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(email=session['email']).first()

    if user is None:
        return redirect(url_for('login'))

    user_id = request.args.get('id')
    email = request.args.get('email')
    full_name = request.args.get('full_name').strip()

    try:
        db.session.execute(f"update [dbo].[SAF_users_table] set is_Approved = 1 where user_id = {user_id}")
        db.session.commit()

        # email = "moses.ikeakhe@sterling.ng"

        SRMS.need = None
        SRMS.message = None

        # print(full_name)

        # full_name = session['full_name']

        SRMS.task = "Signup_Approved"
        SRMS.SendMail(full_name, email)
        result = "User access successfully approved"
    except Exception as e:
        result = "User access approval failed, please try again."
        print(str(e))

    flash(result)

    return redirect(url_for("signuprequest"))


@app.route('/declinerequest', methods=["GET"])
def declinerequest():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))

    user_id = request.args.get('id2')
    email = request.args.get('email2')
    full_name = request.args.get('full_name2').strip()

    try:
        db.session.execute(f"DELETE FROM dbo.SAF_users_table where user_id = {user_id}")
        db.session.commit()

        SRMS.need = None
        SRMS.message = None

        # full_name = session['full_name']

        SRMS.task = "Signup_Declined"
        SRMS.SendMail(full_name, email)
        result = "User access successfully declined"
    except Exception as e:
        print(str(e))
        result = "User access decline failed, please try again."

    flash(result, "success")

    return redirect(url_for("signuprequest"))


@app.route('/approveadminrequest', methods=["GET"])
def approveadminrequest():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))

    user_id = request.args.get('id')

    try:
        db.session.execute(f"update [dbo].[SAF_users_table] set is_Admin = 1 where user_id = {user_id}")
        db.session.commit()
        result = "User admin request successfully approved"
    except Exception as e:
        result = "User admin approval failed, please try again."
        print(str(e))

    flash(result)

    return redirect(url_for("adminrequest"))


@app.route('/revokerequest', methods=["GET", "POST"])
def revokerequest():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))

    data = db.session.execute(
        "select user_id, firstname, Email, lastname, DateLoaded from dbo.SAF_users_table where is_Approved = 1 order by DateLoaded desc")
    result = []

    for data in db.session.query(User).instances(data):
        value = {
            "user_id": data.user_id,
            "Name": f"{data.firstname} {data.lastname}",
            "DateLoaded": data.DateLoaded,
            "Email": data.email
        }

        result.append(value)

    # data = user.query.filter_by(is_Approved=0).order_by(User.DateLoaded).all()
    # print(f"data: {result}")

    return render_template('revokerequest.html', user=session['email'], data=result)


@app.route('/revokerequest2', methods=["GET"])
def revokerequest2():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))

    user_id = request.args.get('id')

    try:
        db.session.execute(f"delete from [dbo].[SAF_users_table] where user_id = {user_id}")
        db.session.commit()
        result = "User access was successfully revoked"
    except Exception as e:
        result = "Revoke user access failed, please try again."
        print(str(e))

    flash(result)

    return redirect(url_for("revokerequest"))


@app.route('/home')
def index():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None
    # print(user)

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('index.html', user=session['email'], admin=session['is_admin'],
                               super_admin=session['is_super_admin'])


@app.route('/brand')
def brand():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.brand()
        # print(f"'data': {data}")
        return render_template('brandperformance.html', user=session['email'], data=data)


@app.route('/igplatform')
def igplatform():
    if 'email' not in session:
        return redirect(url_for('login'))
    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.igplatform()
        # print(f"'Instagram_data': {data}")
        return render_template('igplatform.html', user=session['email'], data=data)


@app.route('/twitterplatform')
def twitterplatform():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.twitterplatform()
        # print(f"'Twitter_data': {data}")
        return render_template('twitterplatform.html', user=session['email'], data=data)


@app.route('/linkedinplatform')
def linkedinplatform():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('linkedinplatform.html', user=session['email'])


@app.route('/fbplatform')
def fbplatform():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        # SRMS.database_connection()  ##### uncomment for facebook
        # data = SRMS.fbplatform()  #### uncomment for facebook and  add data=data to thr return 
        # print(f"'Facebook_data': {data}")
        return render_template('fbplatform.html', user=session['email'])


@app.route('/nlplatform')
def nlplatform():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('nlplatform.html', user=session['email'])


@app.route('/twittertrend')
def twittertrend():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('twittertrend.html', user=session['email'])


@app.route('/igtrend')
def igtrend():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('igtrend.html', user=session['email'])


@app.route('/fbtrend')
def fbtrend():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('fbtrend.html', user=session['email'])


@app.route('/comp')
def comp():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('companalysis.html', user=session['email'])


@app.route('/product')
def product():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('productline.html', user=session['email'])


@app.route('/productall')
def productall():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('productall.html', user=session['email'])


@app.route('/altpower')
def altpower():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            SRMS.database_connection()
            data = SRMS.altpower()
            # print(f"'altpower data': {data}")
            return render_template('altpower.html', user=session['email'], data=data)
    except Exception as e:

        flash("Oops, something went wrong, Please try again...", "danger")

        return render_template('altpower.html', user=session['email'], data=None)


@app.route('/altdrive')
def altdrive():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.altdrive()
        # print(f"'altdrive data': {data}")
        return render_template('altdrive.html', user=session['email'], data=data)


@app.route('/altmall')
def altmall():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.altmall()
        # print(f"'altmall data': {data}")
        return render_template('altmall.html', user=session['email'], data=data)


@app.route('/doubble')
def doubble():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.doubble()
        # print(f"'doubble_data': {data}")
        return render_template('doubble.html', user=session['email'], data=data)


@app.route('/altpay')
def altpay():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        SRMS.database_connection()
        data = SRMS.altpay()
        # print(f"'altpay_data': {data}")
        return render_template('altpay.html', user=session['email'], data=data)


@app.route('/platformall')
def platformall():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('platformall.html', user=session['email'])


@app.route('/feedback')
def feedback():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('feedback.html', user=session['email'])


@app.route('/report')
def report():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        return render_template('report.html', user=session['email'])


@app.route("/selectdatebrand", methods=["GET", "POST"])
def selectdatebrand():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")
        SRMS.database_connection()
        data = SRMS.brand_daterange(startdate, enddate)
        # print(f"'date_range_data': {data}")
        return render_template('branddate.html', user=session['email'], data=data, startdate=startdate, enddate=enddate)


@app.route("/selectdatefb", methods=["GET", "POST"])
def selectdatefb():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")
        SRMS.database_connection()
        data = SRMS.fb_daterange(startdate, enddate)
        # print(f"'fb_date_range_data': {data}")
        return render_template('fbdate.html', user=session['email'], data=data, startdate=startdate, enddate=enddate)


@app.route("/selectdatetwitter", methods=["GET", "POST"])
def selectdatetwitter():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")
        SRMS.database_connection()
        data = SRMS.twitter_daterange(startdate, enddate)
        # print(f"'twitter_date_range_data': {data}")
        return render_template('twitterdate.html', user=session['email'], data=data, startdate=startdate,
                               enddate=enddate)


@app.route("/selectdateig", methods=["GET", "POST"])
def selectdateig():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")
        SRMS.database_connection()
        data = SRMS.ig_daterange(startdate, enddate)
        # print(f"'ig_date_range_data': {data}")
        return render_template('igdate.html', user=session['email'], data=data, startdate=startdate, enddate=enddate)


@app.route("/selectdatealtpower", methods=["GET", "POST"])
def selectdatealtpower():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()
            data = SRMS.daterange_altpower(startdate, enddate)
            # print(f"'Specta_date_range_data': {data}")
            return render_template('altpowerdate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpowerdate.html', user=session['email'], data=None)


@app.route("/selectdatedoubble", methods=["GET", "POST"])
def selectdatedoubble():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")

        SRMS.database_connection()
        data = SRMS.daterange_doubble(startdate, enddate)
        # print(f"'doubble_date_range_data': {data}")
        return render_template('doubledate.html', user=session['email'], data=data, startdate=startdate,
                               enddate=enddate)


@app.route("/selectdatealtpay", methods=["GET", "POST"])
def selectdatealtpay():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")

        SRMS.database_connection()
        data = SRMS.daterange_altpay(startdate, enddate)
        # print(f"'altpay_date_range_data': {data}")
        return render_template('altpaydate.html', user=session['email'], data=data, startdate=startdate,
                               enddate=enddate)


@app.route("/selectdatealtmall", methods=["GET", "POST"])
def selectdatealtmall():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")

        SRMS.database_connection()
        data = SRMS.daterange_altmall(startdate, enddate)
        # print(f"'altmall_date_range_data': {data}")
        return render_template('altmalldate.html', user=session['email'], data=data, startdate=startdate,
                               enddate=enddate)


@app.route("/selectdatealtdrive", methods=["GET", "POST"])
def selectdatealtdrive():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        startdate = request.form.get("startdate")
        enddate = request.form.get("enddate")

        SRMS.database_connection()
        data = SRMS.daterange_altdrive(startdate, enddate)
        # print(f"'Altdrive_date_range_data': {data}")
        return render_template('altdrivedate.html', user=session['email'], data=data, startdate=startdate,
                               enddate=enddate)


@app.route("/feedbackentry", methods=["GET", "POST"])
def feedbackentry():
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        name = request.form.get("name")
        surname = request.form.get("surname")
        email = request.form.get("email")
        need = request.form.get("need")
        message = request.form.get("message")
        full_name = f"{name} {surname}"
        SRMS.database_connection()
        data = SRMS.feedback(full_name, email, need, message)
        SRMS.task = "Feedback_Team"
        SRMS.need = need
        SRMS.message = message
        SRMS.SendMail(full_name, email)

        SRMS.need = None
        SRMS.message = None

        SRMS.task = "Feedback_User"
        SRMS.SendMail(full_name, email)

        if data[0]:
            flash(data[1], "success")
            return render_template('feedback.html', user=session['email'])

        else:
            flash(data[1], "danger")
            return render_template('feedback.html', user=session['email'])


@app.route('/brandsentiment', methods=["GET", "POST"])
def brandsentiment():
    # for brand performance
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        if "pos" in request.form:
            sentiment = "Positive"
        elif "neg" in request.form:
            sentiment = "Negative"
        elif 'neut' in request.form:
            sentiment = "Neutral"
        else:
            return redirect(url_for('brand'))

        SRMS.database_connection()

        data = SRMS.brand_filter_by_sentiment(sentiment)

        return render_template('brandperformance.html', user=session['email'], data=data)


@app.route('/facebooksentiment', methods=["GET", "POST"])
def facebooksentiment():
    # for brand performance
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        if "pos" in request.form:
            sentiment = "Positive"
        elif "neg" in request.form:
            sentiment = "Negative"
        elif 'neut' in request.form:
            sentiment = "Neutral"
        else:
            return redirect(url_for('fbplatform'))

        SRMS.database_connection()

        data = SRMS.facebook_filter_by_sentiment(sentiment)

        return render_template('fbplatform.html', user=session['email'], data=data)


@app.route('/twittersentiment', methods=["GET", "POST"])
def twittersentiment():
    # for brand performance
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        if "pos" in request.form:
            sentiment = "Positive"
        elif "neg" in request.form:
            sentiment = "Negative"
        elif 'neut' in request.form:
            sentiment = "Neutral"
        else:
            return redirect(url_for('twitterplatform'))

        SRMS.database_connection()

        data = SRMS.twitter_filter_by_sentiment(sentiment)

        return render_template('twitterplatform.html', user=session['email'], data=data)


@app.route('/instagramsentiment', methods=["GET", "POST"])
def instagramsentiment():
    # for brand performance
    if 'email' not in session:
        return redirect(url_for('login'))

    try:
        user = User.query.filter_by(email=session['email']).first()
    except Exception as e:
        print(str(e))
        user = None

    if user is None:
        return redirect(url_for('login'))
    else:
        if "pos" in request.form:
            sentiment = "Positive"
        elif "neg" in request.form:
            sentiment = "Negative"
        elif 'neut' in request.form:
            sentiment = "Neutral"
        else:
            return redirect(url_for('igplatform'))

        SRMS.database_connection()

        data = SRMS.instagram_filter_by_sentiment(sentiment)

        return render_template('igplatform.html', user=session['email'], data=data)


@app.route('/altpowersentiment', methods=["GET", "POST"])
def altpowersentiment():
    try:
        # for brand performance
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                return redirect(url_for('altpower'))

            SRMS.database_connection()

            data = SRMS.altpower_filter_by_sentiment(sentiment)

            return render_template('altpower.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpower.html', user=session['email'], data=None)


@app.route('/altpowerchannel', methods=["GET", "POST"])
def altpowerchannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                return redirect(url_for('altpower'))

            SRMS.database_connection()

            data = SRMS.altpower_filter_by_channel(platform)

            return render_template('altpower.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))
        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpower.html', user=session['email'], data=None)


@app.route('/altpaysentiment', methods=["GET", "POST"])
def altpaysentiment():
    try:
        # for brand performance
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                return redirect(url_for('altpay'))

            SRMS.database_connection()

            data = SRMS.altpay_filter_by_sentiment(sentiment)

            return render_template('altpay.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpay.html', user=session['email'], data=None)


@app.route('/altpaychannel', methods=["GET", "POST"])
def altpaychannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                return redirect(url_for('altpay'))

            SRMS.database_connection()

            data = SRMS.altpay_filter_by_channel(platform)

            return render_template('altpay.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpay.html', user=session['email'], data=None)


@app.route('/altmallsentiment', methods=["GET", "POST"])
def altmallsentiment():
    try:
        # for brand performance
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                return redirect(url_for('altmall'))

            SRMS.database_connection()

            data = SRMS.altmall_filter_by_sentiment(sentiment)

            return render_template('altmall.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altmall.html', user=session['email'], data=None)


@app.route('/altmallchannel', methods=["GET", "POST"])
def altmallchannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                return redirect(url_for('altmall'))

            SRMS.database_connection()

            data = SRMS.altmall_filter_by_channel(platform)

            return render_template('altmall.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altmall.html', user=session['email'], data=None)


@app.route('/altdrivesentiment', methods=["GET", "POST"])
def altdrivesentiment():
    try:
        # for brand performance
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                return redirect(url_for('altdrive'))

            SRMS.database_connection()

            data = SRMS.altdrive_filter_by_sentiment(sentiment)

            return render_template('altdrive.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altdrive.html', user=session['email'], data=None)


@app.route('/altdrivechannel', methods=["GET", "POST"])
def altdrivechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                return redirect(url_for('altdrive'))

            SRMS.database_connection()

            data = SRMS.altdrive_filter_by_channel(platform)

            return render_template('altdrive.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altdrive.html', user=session['email'], data=None)


@app.route('/doubblesentiment', methods=["GET", "POST"])
def doubblesentiment():
    try:
        # for brand performance
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                return redirect(url_for('doubble'))

            SRMS.database_connection()

            data = SRMS.doubble_filter_by_sentiment(sentiment)

            return render_template('doubble.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('doubble.html', user=session['email'], data=None)


@app.route('/doubblechannel', methods=["GET", "POST"])
def doubblechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                return redirect(url_for('doubble'))

            SRMS.database_connection()

            data = SRMS.doubble_filter_by_channel(platform)

            return render_template('doubble.html', user=session['email'], data=data)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('doubble.html', user=session['email'], data=None)


@app.route('/branddatesentiment', methods=["GET", "POST"])
def branddatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'
                # return redirect(url_for('selectdatebrand'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.brand_daterange(startdate, enddate)
            else:
                data = SRMS.brand_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            # print(data)

            return render_template('branddate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('branddate.html', user=session['email'], data=None)


@app.route('/twitterdatesentiment', methods=["GET", "POST"])
def twitterdatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'
                # return redirect(url_for('selectdatetwitter'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.twitter_daterange(startdate, enddate)
            else:
                data = SRMS.twitter_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('twitterdate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('twitterdate.html', user=session['email'], data=None)


@app.route('/facebookdatesentiment', methods=["GET", "POST"])
def facebookdatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.fb_daterange(startdate, enddate)
            else:
                data = SRMS.facebook_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('fbdate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('fbdate.html', user=session['email'], data=None)


@app.route('/instagramdatesentiment', methods=["GET", "POST"])
def instagramdatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'
                # return redirect(url_for('selectdateig'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.ig_daterange(startdate, enddate)
            else:
                data = SRMS.instagram_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            # print(data)

            return render_template('igdate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('igdate.html', user=session['email'], data=None)


@app.route('/altpowerdatesentiment', methods=["GET", "POST"])
def altpowerdatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'
                # return redirect(url_for('selectdatespecta'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.daterange_altpower(startdate, enddate)
            else:
                data = SRMS.altpower_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('altpowerdate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpowerdate.html', user=session['email'], data=None)


@app.route('/altpowerdatechannel', methods=["GET", "POST"])
def altpowerdatechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                platform = 'All'
                # return redirect(url_for('selectdatespecta'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if platform == 'All':
                data = SRMS.daterange_altpower(startdate, enddate)
            else:
                data = SRMS.altpower_daterange_filter_by_channel(platform, startdate, enddate)

            return render_template('altpowerdate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpowerdate.html', user=session['email'], data=None)


@app.route('/doubbledatesentiment', methods=["GET", "POST"])
def doubbledatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'
                # return redirect(url_for('selectdatedoubble'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.daterange_doubble(startdate, enddate)
            else:
                data = SRMS.doubble_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('doubledate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('doubledate.html', user=session['email'], data=None)


@app.route('/doubbledatechannel', methods=["GET", "POST"])
def doubbledatechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                platform = 'All'
                # return redirect(url_for('selectdatedoubble'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if platform == 'All':
                data = SRMS.daterange_doubble(startdate, enddate)
            else:
                data = SRMS.doubble_daterange_filter_by_channel(platform, startdate, enddate)

            return render_template('doubledate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('doubledate.html', user=session['email'], data=None)


@app.route('/altmalldatesentiment', methods=["GET", "POST"])
def altmalldatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = "All"
                # return redirect(url_for('selectdateonebank'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.daterange_altmall(startdate, enddate)
            else:
                data = SRMS.altmall_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('altmalldate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altmalldate.html', user=session['email'], data=None)


@app.route('/altmalldatechannel', methods=["GET", "POST"])
def altmalldatechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                platform = 'All'
                # return redirect(url_for('selectdateonebank'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()
            if platform == 'All':
                data = SRMS.daterange_altmall(startdate, enddate)
            else:
                data = SRMS.altmall_daterange_filter_by_channel(platform, startdate, enddate)

            return render_template('altmalldate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altmalldate.html', user=session['email'], data=None)


@app.route('/altdrivedatesentiment', methods=["GET", "POST"])
def altdrivedatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'
                # return redirect(url_for('selectdateonepay'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if sentiment == 'All':
                data = SRMS.daterange_altdrive(startdate, enddate)
            else:
                data = SRMS.altdrive_daterarangenge_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('altdrivedate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altdrivedate.html', user=session['email'], data=None)


@app.route('/altdrivedatechannel', methods=["GET", "POST"])
def altdrivedatechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                platform = 'All'
                # return redirect(url_for('selectdateonepay'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if platform == 'All':
                data = SRMS.daterange_altdrive(startdate, enddate)
            else:
                data = SRMS.altdrive_daterange_filter_by_channel(platform, startdate, enddate)

            return render_template('altdrivedate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altdrivedate.html', user=session['email'], data=None)


@app.route('/altpaydatesentiment', methods=["GET", "POST"])
def altpaydatesentiment():
    try:

        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "pos" in request.form:
                sentiment = "Positive"
            elif "neg" in request.form:
                sentiment = "Negative"
            elif 'neut' in request.form:
                sentiment = "Neutral"
            else:
                sentiment = 'All'

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()
            if sentiment == 'All':
                data = SRMS.daterange_altpay(startdate, enddate)
            else:
                data = SRMS.altpay_daterange_filter_by_sentiment(sentiment, startdate, enddate)

            return render_template('altpaydate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpaydate.html', user=session['email'], data=None)


@app.route('/altpaydatechannel', methods=["GET", "POST"])
def altpaydatechannel():
    try:
        if 'email' not in session:
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(email=session['email']).first()
        except Exception as e:
            print(str(e))
            user = None

        if user is None:
            return redirect(url_for('login'))
        else:
            if "fb" in request.form:
                platform = "Facebook"
            elif "ig" in request.form:
                platform = "Instagram"
            elif "twitter" in request.form:
                platform = "Twitter"
            else:
                platform = 'All'
                # return redirect(url_for('selectdateiinvest'))

            startdate = request.form.get("startdate")
            enddate = request.form.get("enddate")

            SRMS.database_connection()

            if platform == 'All':
                data = SRMS.daterange_altpay(startdate, enddate)
            else:
                data = SRMS.altpay_daterange_filter_by_channel(platform, startdate, enddate)

            return render_template('altpaydate.html', user=session['email'], data=data, startdate=startdate,
                                   enddate=enddate)
    except Exception as e:
        print(str(e))

        flash("Oops something went wrong, Please try again...", "danger")

        return render_template('altpaydate.html', user=session['email'], data=None)
