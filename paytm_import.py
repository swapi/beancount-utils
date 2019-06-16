import datetime
import csv
import sys
import decimal


class ProcessingStatus:
    PROCESSED = 0
    SKIPPED = 1


class PaytmAccountCategorizer(object):
    def __init__(self):
        self.travel = set(['UBER', 'IRCTC E Ticketing'])
        self.bills = set(['Reliance Jio'])
        self.food = set(['Box8', 'McD Magarpatta Pune', 'Zomato'])
        self.groceries = set(['Real Mart'])

    def categorize(self, where):
        if where in self.travel:
            return 'Expenses:Travel'
        elif where in self.food:
            return 'Expenses:Food'
        elif where in self.bills:
            return 'Expenses:Bills:Phone'
        elif where in self.groceries:
            return 'Expenses:Groceries'
        elif where == 'Cashback':
            return 'Income:Cashback:Paytm'
        return 'Expenses:Uncategorized'

class PaytmProcessor(object):
    def __init__(self, categorizer,
                 paytm_account='Assets:Paytm'):
        self.on_hold = {}
        self.categorizer = categorizer
        self.paytm_account = paytm_account
        self.last_result = None

    def trx_id(self, trx):
        return trx[2]

    def should_skip(self, trx):
        activity = trx[1]
        id = trx[2]
        status = trx[-1]

        if activity == 'On Hold For Order':
            # ignore hold and corresponding refund trx
            self.on_hold[id] = status
            return True
        elif id in self.on_hold.keys():
            if activity == 'Refunded Back':
                return True
        elif status not in 'SUCCESS':
            return True
        elif activity == 'Added To Paytm Account':
            # if money is transferred from savings to paytm
            # ignore it, it will be taken care in savings account
            return True
        return False

    def process(self, trx):
        self.last_result = None
        if self.should_skip(trx):
            return ProcessingStatus.SKIPPED

        trxdate = datetime.datetime.strptime(trx[0], '%d/%m/%Y %H:%M:%S')
        activity = trx[1]
        order = trx[2].split('Order #')[0].strip()
        comment = trx[4]
        debit_amount = trx[5]
        credit_amount = trx[6]

        where = None
        if activity == 'Cashback Received':
            where = 'Cashback'
        where = where or order or comment

        amount = decimal.Decimal(0)
        if debit_amount:
            amount -= decimal.Decimal(debit_amount)
        if credit_amount:
            amount += decimal.Decimal(credit_amount)

        self.last_result = (trxdate, where, amount)

        return ProcessingStatus.PROCESSED

    def format_last_result(self):
        # TODO instead of relying on last_result, this should
        # be parameter (whose value returned by process)
        if not self.last_result:
            return

        trxdate = self.last_result[0]
        where = self.last_result[1]
        amount = self.last_result[2]

        account = self.categorizer.categorize(where)

        fmtdate = trxdate.strftime('%Y-%m-%d')
        return """%s * "Paytm" "%s"
        %s                      %s INR
        %s
        """ % (fmtdate, where, self.paytm_account, str(amount), account)


if len(sys.argv) < 1:
    print('paytm-import <csv-file>')
    sys.exit(-1)

paytm_file = sys.argv[-1]
if not paytm_file.endswith('.csv'):
    print('paytm-import <csv-file>')
    sys.exit(-1)

p = PaytmProcessor(PaytmAccountCategorizer())
with open(paytm_file) as f:
    paytm_reader = csv.reader(f)
    next(paytm_reader) # skip header

    trxs = []
    for trx in paytm_reader:
        trxs += [trx]

    trxs.reverse()
    for trx in trxs:
        r = p.process(trx)
        if r == ProcessingStatus.PROCESSED:
            print(p.format_last_result())
