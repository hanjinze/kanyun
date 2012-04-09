#!/usr/bin/env python
# encoding: utf-8
# TAB char: space
# Task ventilator
# Binds PUSH socket to tcp://localhost:5557
# Sends batch of tasks to workers via that socket
#
# Author: Peng Yuwei<yuwei5@staff.sina.com.cn> 2012-3-27
# Last update: Peng Yuwei<yuwei5@staff.sina.com.cn> 2012-3-28

import sys
import time
import types
import json
import traceback
import ConfigParser
import zmq
from collections import OrderedDict
from kanyun.common.const import *
from kanyun.database.cassadb import CassaDb

"""
Save the vm's system info data to db.
                         +--- <-- Worker's PUSH
                         |
                         |
                   +----------+
                   |   PULL   |     <-- feedback
               +---|==========|
   Client--->  |REP|  Server  |
               +---|==========|
                   |   PUB    |     <-- broadcast
                   +----------+
                         |
                         |
                         +----> Worker's SUB
                         +----> DB

protocol:
    http://wiki.sinaapp.com/doku.php?id=monitoring
[u'S', u'instance-00000001@pyw.novalocal', u'cpu', u'total', 0, 5, 1332897600, 0]
"""


class Statistics():
    def __init__(self):
        self.clean()
    def clean(self):
        self.first = True
        self.count = 0
        self.sum = 0.0
        self.min = 0.0
        self.max = 0.0
        self.previous = 0.0
        self.diff = 0.0
        
    def update(self, value):
        self.count += 1
        self.sum += value
        if self.first:
            self.first = False
            self.previous = value
            self.max = value
            self.min = value
            return
            
        if value > self.previous:
            self.max = value
        elif value < self.previous:
            self.min = value
        self.diff = value - self.previous
        self.previous = value
    def get_value(self, which):
        if which == STATISTIC.AVERAGE:
            return self.get_agerage()
        elif which == STATISTIC.MINIMUM:
            return self.get_min()
        elif which == STATISTIC.MAXIMUM:
            return self.get_max()
        elif which == STATISTIC.SUM:
            return self.get_sum()
        elif which == STATISTIC.SAMPLES:
            return self.get_samples()
        else:
            print 'error:', which
            return 0
            
    def get_diff(self):
        return self.diff;
    def get_agerage(self):
        if self.count == 0:
            return 0
        else:
            return self.sum / self.count
    def get_sum(self):
        return self.sum
    def get_max(self):
        return self.max
    def get_min(self):
        return self.min
    def get_samples(self):
        # TODO
        return 0;


"""cassandra database object"""
db = None
"""
# ColumnFamilys object collection
# data format: {key: ColumnFamily Object}
# example: {'cpu', ColumnFamily()}
"""

def get_db():
    global db
    if db is None:
        config = ConfigParser.ConfigParser()
        config.read("kanyun.conf")
        api_cfg = dict(config.items('api'))
        db = CassaDb('data', api_cfg['db_host'])
    return db
    
def api_getdata(row_id, cf_str, scf_str, time_from=0, time_to=0):
    """
    return: recordset, count, bool(count > limit?)
    """
    if not type(row_id) is types.UnicodeType \
        or not type(cf_str) is types.UnicodeType \
        or not type(scf_str) is types.UnicodeType \
        or not type(time_from) is types.IntType \
        or not type(time_to) is types.IntType:
        return None, 0, True
        
    db = get_db()
        
    if time_to == 0:
        time_to = time.time()
    
    rs = db.get(cf_str, row_id, super_column=scf_str, column_start=time_from, column_finish=int(float(time_to)), column_count=20000)
    count = 0 if rs is None else len(rs)
    
    return rs, count, False if (count == 20000) else True
    
def analyize_data(rs, period, statistic):
    """[private func]analyize the data"""
    if rs is None or not type(period) is types.IntType or not type(statistic) is types.IntType:
        return None
    t = 0
    key_time = 0
    st = Statistics()
    this_period = dict()
    
    for timestmp, value in rs.iteritems():
        rt = time.gmtime(timestmp)
        key = rt.tm_min + rt.tm_hour*100 + rt.tm_mday*10000 + rt.tm_mon*1000000 + rt.tm_year*100000000
        if t == 0:
            print '\tget first value'
            st.clean()
            t = key
            key_time = time.gmtime(timestmp)
        if key >= t + period:
            print '\tnext'
            st.clean()
            t = key
            key_time = time.gmtime(timestmp)
        st.update(float(value))
        key2 = time.mktime((key_time.tm_year, key_time.tm_mon, key_time.tm_mday, key_time.tm_hour, key_time.tm_min,0,0,0,0))
        this_period[key2] = st.get_value(statistic)
        print '\tcompute time=%d, value=%s(%f) "update(%s)=%d"' % \
                (key, value, float(value), key2, this_period[key2])
            
    this_period = OrderedDict(sorted(this_period.items(), key=lambda t: t[0]))
    print statistic, ":each period(", period, "):"
    for m, val in this_period.iteritems():
        rt = time.gmtime(m)
        key = rt.tm_min + rt.tm_hour*100 + rt.tm_mday*10000 + rt.tm_mon*1000000 + rt.tm_year*100000000
        print '\t', key, m, val
        
    return this_period

############################# public API interface #############################
def api_getInstancesList(cf_str):
    if not type(cf_str) is types.UnicodeType:
        print 'param types error'
        return None
    ret = list()
    limit = 20000
    time_to = time.time()
    time_from = time_to - 24 * 60 * 60
    db = get_db()
    
    rs = db.get_range(cf_str)
    if not rs is None:
        for i in rs:
            ret.append(i[0])
    
    return ret
    
def api_getbyInstanceID(row_id, cf_str):
    if not type(row_id) is types.UnicodeType \
        or not type(cf_str) is types.UnicodeType:
        print 'param types error'
        return None, 0, True
    db = get_db()
    rs = db.getbykey(cf_str, row_id)
    count = 0 if rs is None else len(rs)
    
    return rs, count, False if (count == 20000) else True
    
    
def api_getbykey(row_id, cf_str, scf_str, limit=20000):
    """
    example:cf=vmnetwork,scf=10.0.0.1,key=instance-0000002
    return: recordset, count, bool(count > limit?)
    """
    if not type(row_id) is types.UnicodeType \
        or not type(cf_str) is types.UnicodeType \
        or not type(scf_str) is types.UnicodeType \
        or not type(limit) is types.IntType:
        print 'param types error'
        return None, 0, True
    db = get_db()
    rs = db.getbykey2(cf_str, key=row_id, super_column=scf_str, column_count=limit)
    count = 0 if rs is None else len(rs)
    
    return rs, count, False if (count == 20000) else True

def api_statistic(row_id, cf_str, scf_str, statistic, period=5, time_from=0, time_to=0):
    """statistic is STATISTIC enum
    period default=5 minutes
    time_to default=0(now)"""
    if not type(row_id) is types.UnicodeType \
        or not type(cf_str) is types.UnicodeType \
        or not type(scf_str) is types.UnicodeType \
        or not type(statistic) is types.IntType \
        or not type(period) is types.IntType \
        or not type(time_from) is types.IntType \
        or not type(time_to) is types.IntType:
        print 'param types error'
        return None, 0, True
        
    ret_len = 0
    rs, count, all_data = api_getdata(row_id, cf_str, scf_str, time_from, time_to)
    if not rs is None and count > 0:
        buf = analyize_data(rs, 1, statistic)
        ret = analyize_data(buf, period, statistic)
        ret_len = 0 if ret is None else len(ret)
        print ret_len, "result."
    else:
        print "no result."
        ret = None
        ret_len = 0
    return ret, ret_len, all_data

########################## end public API interface #############################
