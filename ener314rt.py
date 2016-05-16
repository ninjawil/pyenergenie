# ener314rt.py  27/09/2015  D.J.Whale


#!/usr/bin/env python

'''Monitor settings of Energine MiHome plugs'''


#===============================================================================
# Import modules
#===============================================================================

# Standard Library
import os
import sys
import time

# Third party modules
from energenie import OpenHEMS, Devices
from energenie import radio

# Application modules
import logging
import logging.handlers
from messages import MESSAGE_JOIN_ACK, MESSAGE_SWITCH


#===============================================================================
class MiPlug:
 
    '''Sets up the comms'''
 
    def __init__(self, mfrid= Devices.MFRID_ENERGENIE, 
                    productid= Devices.PRODUCTID_R1_MONITOR_AND_CONTROL, 
                    sensorid= 0):
        
        self.logger = logging.getLogger('root')

        self.directory = {}

        self.msg_join_ack = MESSAGE_JOIN_ACK
        self.msg_join_ack['header']['mfrid'] = mfrid
        self.msg_join_ack['header']['productid'] = productid
        self.msg_join_ack['header']['sensorid'] = sensorid

        self.msg_switch = MESSAGE_SWITCH
        self.msg_switch['header']['sensorid'] = sensorid
        
        radio.init()
        OpenHEMS.init(Devices.CRYPT_PID)
        
 
    #---------------------------------------------------------------------------
    # Create short message
    #---------------------------------------------------------------------------
    def clean(self, msg):

        '''Takes message returned from radio and returns a dictionary with
        only essential values'''

        data = {'timestamp': 'U',
                'mfrid': 'U',
                'productid': 'U',
                'sensorid': 'U',
                'switch': 'U',
                'voltage': 'U',
                'freq': 'U',
                'reactive': 'U',
                'real': 'U' }

        # get the header
        header    = msg['header']
        data['timestamp'] = int(time.time())
        data['mfrid']     = header['mfrid']
        data['productid'] = header['productid']
        data['sensorid']  = header['sensorid']

        # capture any data that we want
        for rec in msg['recs']:
            paramid = rec['paramid']
            try:
                value = rec['value']
            except:
                value = None
                
            if   paramid == OpenHEMS.PARAM_SWITCH_STATE:
                data['switch'] = value
            elif paramid == OpenHEMS.PARAM_VOLTAGE:
                data['voltage'] = value
            elif paramid == OpenHEMS.PARAM_FREQUENCY:
                data['freq'] = value
            elif paramid == OpenHEMS.PARAM_REACTIVE_POWER:
                data['reactive'] = value
            elif paramid == OpenHEMS.PARAM_REAL_POWER:
                data['real'] = value

        return data


    #---------------------------------------------------------------------------
    # Write data to CSV file
    #---------------------------------------------------------------------------
    def updateCSV (self, msg, log_filename='energenie.csv'):
        
        '''Writes message data to CSV file'''
        
        HEADINGS = 'timestamp,mfrid,prodid,sensorid,flags,switch,voltage,freq,reactive,real'

        log_file = None

        if 'header' in msg:
            msg = self.clean(msg)

        if log_file == None:
            if not os.path.isfile(log_filename):
                log_file = open(log_filename, 'w')
                log_file.write(HEADINGS + '\n')
            else:
                log_file = open(log_filename, 'a') # append

        flags= [1,1,1,1,1]

        if msg['switch'] == 'U':
            flags[0] = 0
        if msg['voltage'] == 'U':
            flags[1] = 0
        if msg['freq'] == 'U':
            flags[2] = 0
        if msg['reactive'] == 'U':
            flags[3] = 0
        if msg['real'] == 'U':
            flags[4] = 0

        csv = '{timestamp}, {mfrid}, {productid}, {sensorid}, {flags}, {switch}, {voltage}, {freq}, {reactive}, {real}'.format(
                timestamp= msg['timestamp'],
                mfrid= msg['mfrid'],
                productid= msg['productid'],
                sensorid= msg['sensorid'],
                flags= "".join([str(a) for a in flags]),
                switch= msg['switch'],
                voltage= msg['voltage'],
                freq= msg['freq'],
                reactive= msg['reactive'],
                real= msg['real'])

        log_file.write(csv + '\n')
        log_file.flush()
        self.logger.info(csv) # testing


    #---------------------------------------------------------------------------
    # 
    #---------------------------------------------------------------------------
    def allkeys(self, d):
        result = ""
        for k in d:
            if len(result) != 0:
                result += ','
            result += str(k)
        return result


    #---------------------------------------------------------------------------
    # Update Directory
    #---------------------------------------------------------------------------
    def updateDirectory(self, message):

        '''Update the local directory with information about this device'''

        now      = time.time()
        header   = message["header"]
        sensorId = header["sensorid"]

        if not self.directory.has_key(sensorId):
            # new device discovered
            desc = Devices.getDescription(header["mfrid"], header["productid"])
            self.logger.info("ADD device:%s %s" % (hex(sensorId), desc))
            self.directory[sensorId] = {"header": message["header"]}
            self.logger.info(self.allkeys(self.directory))

        self.directory[sensorId]["time"] = now
        #TODO would be good to keep recs, but need to iterate through all and key by paramid,
        #not as a list index, else merging will be hard.



    #---------------------------------------------------------------------------
    # Grab data
    #---------------------------------------------------------------------------
    def get_data(self, monitor_mode= False, short_msg= True):

        '''Send discovery and monitor messages, and capture any responses.
            monitor_mode    True:   will loop continously
                            False:  will stop script once first succesful data 
                                    packet is received (default)
            short_msg       True:   returns long detailed message
                            False:  returns short message (default)'''

        # Define the schedule of message polling
        radio.receiver()
        decoded            = None
        message_not_received = True
        attempt_count = 2

        while message_not_received:
            # See if there is a payload, and if there is, process it
            if radio.isReceiveWaiting():
                self.logger.info("receiving payload")
                payload = radio.receive()

                if monitor_mode == False:
                    message_not_received = False

                try:
                    decoded = OpenHEMS.decode(payload)
                except OpenHEMS.OpenHEMSException as e:
                    self.logger.error("Attempt: {attempt} - Can't decode payload: {msg}".format(
                                            attempt = attempt_count,
                                            msg = str(e)))
                    if receive_attempt > 0:
                        message_not_received = True
                        attempt_count = attempt_count - 1
                    continue
                          
                self.updateDirectory(decoded)

                if self.msg_join_ack['header']['sensorid'] == 0 or self.msg_switch['header']['sensorid'] == 0:
                    self.msg_join_ack['header']['sensorid'] = decoded["header"]["sensorid"] 
                    self.msg_switch['header']['sensorid']   = decoded["header"]["sensorid"]
                
                #TODO: Should remember report time of each device,
                #and reschedule command messages to avoid their transmit slot
                #making it less likely to miss an incoming message due to
                #the radio being in transmit mode

                # assume only 1 rec in a join, for now
                if len(decoded["recs"])>0 and decoded["recs"][0]["paramid"] == OpenHEMS.PARAM_JOIN:
                    #TODO: write OpenHEMS.getFromMessage("header_mfrid")
                    response = OpenHEMS.alterMessage(self.msg_join_ack,
                        header_mfrid=decoded["header"]["mfrid"],
                        header_productid=decoded["header"]["productid"],
                        header_sensorid=decoded["header"]["sensorid"])
                    p = OpenHEMS.encode(response)
                    radio.transmitter()
                    radio.transmit(p)
                    radio.receiver()

        if short_msg:
            decoded = self.clean(decoded)
            
        return decoded


    #---------------------------------------------------------------------------
    # Send data to switch
    #---------------------------------------------------------------------------
    def send_data(self, switch_state):

        '''Send data to switch'''

        request = OpenHEMS.alterMessage(self.msg_switch, recs_0_value=switch_state)
        p = OpenHEMS.encode(request)
        radio.transmitter()
        radio.transmit(p)
        radio.receiver()
 
        
    #---------------------------------------------------------------------------
    # Finish comms
    #---------------------------------------------------------------------------
    def close(self):

        '''Closes connection'''

        radio.finished()


#===============================================================================
# MAIN
#===============================================================================
def main():
   
    '''Entry point for script'''

    script_name = os.path.basename(sys.argv[0])


    #---------------------------------------------------------------------------
    # Set up logger
    #---------------------------------------------------------------------------
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)-8s] %(module)-15s : %(message)s')
    logging.Formatter.converter = time.gmtime
    
    fh = logging.handlers.TimedRotatingFileHandler(filename='{script}.log'.format(
                                                                script= script_name[:-3]), 
                                                    when='midnight', 
                                                    backupCount=7, 
                                                    utc=True)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    
    logger = logging.getLogger('root')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info('')
    logger.info('--- Script {script} Started ---'.format(script= script_name)) 
    

    #---------------------------------------------------------------------------
    # Set up radio and capture data
    #---------------------------------------------------------------------------
    plug = MiPlug()

    try:
        data = plug.get_data()
        plug.updateCSV(data)
        plug.send_data(True)

    finally:
        plug.close()



#===============================================================================
# Boiler plate
#===============================================================================
if __name__=='__main__':
    main()
