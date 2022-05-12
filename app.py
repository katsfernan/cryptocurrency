import datetime
from http.client import HTTPException
import json
from flask import Flask, jsonify, request 
from dotenv import load_dotenv
from flask_marshmallow import Marshmallow

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

import requests
import os

load_dotenv()
app = Flask (__name__)

#Variables de entorno para proteger credenciales
POSTGRE_USER_PASSWORD = os.getenv("POSTGRE_USER_PASSWORD")
POSTGRE_DATABASE_NAME = os.getenv("POSTGRE_DATABASE_NAME")
#Conexion a motor de base de datos Postgresql
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://postgres:{POSTGRE_USER_PASSWORD}@localhost/{POSTGRE_DATABASE_NAME}"

#Instancias de Base de datos y Marshmallow para los schemas
db = SQLAlchemy(app)
ma = Marshmallow(app)


#Modelos
class Transaction (db.Model):
    id = db.Column(db.Integer,primary_key = True)
    currency_amount = db.Column(db.Float)
    money_amount = db.Column(db.Float)
    date_transaction = db.Column(db.DateTime)
    currency_id = db.Column(db.Integer, db.ForeignKey('currency.id'))
    money_id = db.Column(db.Integer, db.ForeignKey('currency.id'))
    wallet_id = db.Column(db.Integer, db.ForeignKey('wallet.id'))

class Currency(db.Model):
    id = db.Column(db.Integer,primary_key = True)
    code = db.Column(db.String)
    name = db.Column(db.String)

class Wallet(db.Model):
    id = db.Column(db.Integer,primary_key = True)
    balance = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    wallet_id = db.relationship('Wallet')

#Schemmas
class TransactionSchema(ma.Schema):
    class Meta:
        fields = ('currency_amount', 'money_amount', 'date_transaction', 'currency_id', 'money_id', 'wallet_id')

class WalletSchema(ma.Schema):
    class Meta:
        fields = ('id','balance')

#Instancias de Schemas
transaction_schema = TransactionSchema()
wallet_schema = WalletSchema()

coingecko_url_base = 'https://api.coingecko.com/api/v3'

@app.route('/coins/')
def get_currencies():
    """Endpoint que devuelve lista de todas las crypto monedas"""
    coins = []
    response = requests.get(f"{coingecko_url_base}/coins/list")
    for resp in response:
        coins.append(resp.decode('utf8'))
    
    return ({"items":coins})

@app.route('/coins/<id>')
def get_currency(id):
    """Endpoint que devuelve una moneda por id"""
    response = requests.get(f"{coingecko_url_base}/coins/{id}")
    if response:
        return response._content
    return "Can't get currency with id provided", 400

@app.route('/wallet',methods=['GET','POST'])
def wallet_movement():
    """Endpoint para agregar un movimiento en la wallet, la misma recibe un id de usuario, id de crypto moneda, id de id de dinero
    (en este caso solo usd), se valida el metodo para hacer un get o post en la funcion"""

    if request.method  == 'POST':
        if request.json:
            user  = User.query.get(request.json['user']) 
            if user:
                currency = Currency.query.get(request.json['currency_id'])
                money = Currency.query.get(request.json['money_id'])
                wallet = Wallet.query.filter_by(user_id= user.id).first()
                if currency and money and wallet:
                    date = datetime.datetime.now()
                    currency_amount = request.json['currency_amount']
                    money_amount = request.json['money_amount']

                    transaction = Transaction(
                        currency_amount = currency_amount,
                        money_amount = money_amount,
                        date_transaction = date,
                        currency_id = currency.id,
                        money_id = money.id,
                        wallet_id = wallet.id
                    )

                    wallet.balance = money_amount

                    db.session.add(transaction)
                    db.session.add(wallet)
                    db.session.commit()
                    return transaction_schema.jsonify(transaction), 200
                else:
                    return 'Currency does not exist', 400

            return 'No user registered with that id', 400

        return 'No data provided', 400

    args = request.args.get('wallet')
    if args:
        wallet = Wallet.query.get(id = args)
        return wallet_schema.jsonify(wallet), 200
    return 'No wallet provided', 400


def get_currency_price(code):
    """Funcion que realiza una peticion del precio actual de una cryptomoneda"""
    payload = {"ids":code, "vs_currencies":"usd"}
    response = requests.get(f"{coingecko_url_base}/simple/price", params = payload)
    response = response._content
    actual_currency = json.loads(response)
    actual_price = actual_currency[code]["usd"] 
    return actual_price  

def get_currency_wallet(code, wallet):
    """Funcion que recibe un codigo de crypto moneda y un wallet, itera sobre todos los movimientos que el usuario realizo
    en esa crypto moneda y retorna el valor de una unidad de moneda en usd"""
    currency = Currency.query.filter_by(code = code).first()
    if currency:
        transactions = Transaction.query.filter_by(currency_id = currency.id, wallet_id = wallet.id)
        if transactions:
            currency_total = 0
            money_total = 0
            for t in transactions:
                currency_total +=  t.currency_amount 
                money_total += t.money_amount
            
            money_avg =  round(money_total / currency_total, 2)
            return money_avg

        raise HTTPException
    raise HTTPException
     

@app.route('/wallet/statistic')
def wallet_resume():
    """Endpoint para generar un analisis de mercado, primero se valida si se envio un  codigo de crypto moneda, si se hizo,
    se itera sobre todas las transacciones que realizo el usuario en esa moneda y retorna si la tendencia es alcista o bajista, 
    el porcentaje de crecimiento o decrecimiento, y los montos comparados (historico de dinero invertido en la moneda y valor 
    actual de la moneda) """
    user = User.query.filter_by(id=request.json['user']).first()
    if user:
        arg = request.args.get('currency_code')
        wallet = Wallet.query.filter_by(user_id = user.id).first()
        if wallet:
            if arg:
                money_avg = get_currency_wallet(arg,wallet)
                actual_price = get_currency_price(arg)
            else:
                transactions = (db.session.query(
                    Transaction.currency_id
                )).filter_by(wallet_id = wallet.id).group_by(Transaction.currency_id)
                                            
                if transactions:
                    actual_price_total = 0
                    money_avg_total = 0
                    for t in transactions:
                        currency_id = t[0]
                        currency = Currency.query.get(currency_id)
                        actual_price =  get_currency_price(currency.code)
                        money_avg = get_currency_wallet(currency.code,wallet)
                        actual_price_total +=  actual_price
                        money_avg_total += money_avg
                    actual_price = actual_price_total
                    money_avg = money_avg_total

            percentage =  round((actual_price/money_avg*100 - 100),2)
            if money_avg < actual_price:
                trend = 'rising'  
            elif money_avg > actual_price:
                trend = 'low'
            else:
                trend= 'tied'
            
            return jsonify({
                "wallet_avg":money_avg,
                "actual_price":actual_price,
                "trend": trend,
                "percentage":percentage
                })
                
            return 'No transactions available', 400

        return 'The wallet does not exists', 400

    return 'You have no permissions', 401







