#####################################################
# GA17 Privacy Enhancing Technologies -- Lab 02
#
# Basics of Mix networks and Traffic Analysis
#
# Run the tests through:
# $ py.test -v test_file_name.py

#####################################################
# TASK 1 -- Ensure petlib is installed on the System
#           and also pytest. Ensure the Lab Code can 
#           be imported.

from collections import namedtuple
from hashlib import sha512
from struct import pack, unpack
from binascii import hexlify

def aes_ctr_enc_dec(key, iv, input):
    """ A helper function that implements AES Counter (CTR) Mode encryption and decryption. 
    Expects a key (16 byte), and IV (16 bytes) and an input plaintext / ciphertext.

    If it is not obvious convince yourself that CTR encryption and decryption are in 
    fact the same operations.
    """
    
    aes = Cipher("AES-128-CTR") 

    enc = aes.enc(key, iv)
    output = enc.update(input)
    output += enc.finalize()

    return output

#####################################################
# TASK 2 -- Build a simple 1-hop mix client.
#
#


## This is the type of messages destined for the one-hop mix
OneHopMixMessage = namedtuple('OneHopMixMessage', ['ec_public_key', 
                                                   'hmac', 
                                                   'address', 
                                                   'message'])

from petlib.ec import EcGroup
from petlib.hmac import Hmac, secure_compare
from petlib.cipher import Cipher

def mix_server_one_hop(private_key, message_list):
    """ Implements the decoding for a simple one-hop mix. 

        Each message is decoded in turn:
        - A shared key is derived from the message public key and the mix private_key.
        - the hmac is checked against all encrypted parts of the message
        - the address and message are decrypted, decoded and returned

    """
    G = EcGroup()

    out_queue = []

    # Process all messages
    for msg in message_list:


        ## Check elements and lengths
        if not G.check_point(msg.ec_public_key) or \
               not len(msg.hmac) == 20 or \
               not len(msg.address) == 258 or \
               not len(msg.message) == 1002:
           raise Exception("Malformed input message")

        ## First get a shared key
        shared_element = private_key * msg.ec_public_key
        key_material = sha512(shared_element.export()).digest()
	
        # Use different parts of the shared key for different operations
        hmac_key = key_material[:16]
        address_key = key_material[16:32]
        message_key = key_material[32:48]

        ## Check the HMAC
        h = Hmac(b"sha512", hmac_key)        
        h.update(msg.address)
        h.update(msg.message)
        expected_mac = h.digest()

        print "my hmac: " + str(msg.hmac)
        print "ex hmac: " + str(expected_mac[:20])

        if not secure_compare(msg.hmac, expected_mac[:20]):
            raise Exception("HMAC check failure")

        ## Decrypt the address and the message
        iv = b"\x00"*16

        address_plaintext = aes_ctr_enc_dec(address_key, iv, msg.address)
        message_plaintext = aes_ctr_enc_dec(message_key, iv, msg.message)

        # Decode the address and message
        address_len, address_full = unpack("!H256s", address_plaintext)
        message_len, message_full = unpack("!H1000s", message_plaintext)

        output = (address_full[:address_len], message_full[:message_len])
        out_queue += [output]

    return sorted(out_queue)
        
        
def mix_client_one_hop(public_key, address, message):
    """
    Encode a message to travel through a single mix with a set public key. 
    The maximum size of the final address and the message are 256 bytes and 1000 bytes respectively.
    Returns an 'OneHopMixMessage' with four parts: a public key, an hmac (20 bytes),
    an address ciphertext (256 + 2 bytes) and a message ciphertext (1002 bytes). 
    """

    G = EcGroup()
    assert G.check_point(public_key)
    assert isinstance(address, bytes) and len(address) <= 256
    assert isinstance(message, bytes) and len(message) <= 1000

    # Encode the address and message
    # Use those as the payload for encryption
    address_plaintext = pack("!H256s", len(address), address)
    message_plaintext = pack("!H1000s", len(message), message)

    ## Generate a fresh public key
    private_key = G.order().random()
    client_public_key  = private_key * G.generator()

    encryption_key = private_key * public_key
    ek = sha512(encryption_key.export()).digest()
		
    #TODO ADD CODE HERE 	
    
    #get coresponding key parts	
    hmac_key = ek[:16]
    address_key = ek[16:32]
    message_key = ek[32:48]
	 
    #encrypt
    iv = b"\x00"*16
    address_cipher = aes_ctr_enc_dec(address_key, iv, address_plaintext)            
    message_cipher = aes_ctr_enc_dec(message_key, iv, message_plaintext)

    #calculate mac
    h = Hmac(b"sha512", hmac_key)        
    h.update(address_cipher)
    h.update(message_cipher)
    expected_mac = h.digest()
    expected_mac = expected_mac[:20]
      
    return OneHopMixMessage(client_public_key, expected_mac, address_cipher, message_cipher)

    

#####################################################
# TASK 3 -- Build a n-hop mix client.
#           Mixes are in a fixed cascade.
#

from petlib.ec import Bn

# This is the type of messages destined for the n-hop mix
NHopMixMessage = namedtuple('NHopMixMessage', ['ec_public_key', 
                                                   'hmacs', 
                                                   'address', 
                                                   'message'])


def mix_server_n_hop(private_key, message_list, use_blinding_factor=False, final=False):
    """ Decodes a NHopMixMessage message and outputs either messages destined
    to the next mix or a list of tuples (address, message) (if final=True) to be 
    sent to their final recipients.

    Broadly speaking the mix will process each message in turn: 
        - it derives a shared key (using its private_key), 
        - checks the first hmac,
        - decrypts all other parts,
        - Either forwards or decodes the message. 

    The implementation of the blinding factor is optional and therefore only activated 
    in the bonus tests.
    """

    G = EcGroup()

    out_queue = []
		
    # Process all messages
    for msg in message_list:
	
        ## Check elements and lengths
        if not G.check_point(msg.ec_public_key) or \
               not isinstance(msg.hmacs, list) or \
               not len(msg.hmacs[0]) == 20 or \
               not len(msg.address) == 258 or \
               not len(msg.message) == 1002:
           raise Exception("Malformed input message")

        ## First get a shared key
        shared_element = private_key * msg.ec_public_key
        key_material = sha512(shared_element.export()).digest()
	
        # Use different parts of the shared key for different operations
        hmac_key = key_material[:16]
        address_key = key_material[16:32]
        message_key = key_material[32:48]

        # Extract a blinding factor for the public_key 
        # (only if you're brave enough for the bonus task)
        new_ec_public_key = msg.ec_public_key
        if (use_blinding_factor):
            blinding_factor = Bn.from_binary(key_material[48:])
            new_ec_public_key = blinding_factor * msg.ec_public_key

	      
        ## Check the HMAC
        h = Hmac(b"sha512", hmac_key)
	
        for other_mac in msg.hmacs[1:]:
            h.update(other_mac)
	  			
        h.update(msg.address)
        h.update(msg.message)

        expected_mac = h.digest()
	
	#print "server hmac_key  : ", hmac_key
	#print "server addr_key  : ", address_key
	#print "server mesg_key  : ", message_key
	
	#print "server adr_cipher: ", msg.address[:75]
	#print "server msg_cipher: ", msg.message[:75]
	
        if not secure_compare(msg.hmacs[0], expected_mac[:20]):
            raise Exception("HMAC check failure")
	
        ## Decrypt the hmacs, address and the message
        aes = Cipher("AES-128-CTR") 
	
        # Decrypt hmacs
        new_hmacs = []
        for i, other_mac in enumerate(msg.hmacs[1:]):
            # Ensure the IV is different for each hmac
            iv = pack("H14s", i, b"\x00"*14)

            hmac_plaintext = aes_ctr_enc_dec(hmac_key, iv, other_mac)
            new_hmacs += [hmac_plaintext]

        # Decrypt address & message
        iv = b"\x00"*16
        
        address_plaintext = aes_ctr_enc_dec(address_key, iv, msg.address)
        message_plaintext = aes_ctr_enc_dec(message_key, iv, msg.message)

        if final:
            # Decode the address and message
            address_len, address_full = unpack("!H256s", address_plaintext)
            message_len, message_full = unpack("!H1000s", message_plaintext)

            out_msg = (address_full[:address_len], message_full[:message_len])
            out_queue += [out_msg]
        else:
            # Pass the new mix message to the next mix
            out_msg = NHopMixMessage(new_ec_public_key, new_hmacs, address_plaintext, message_plaintext)
            out_queue += [out_msg]

    return out_queue


def mix_client_n_hop(public_keys, address, message, use_blinding_factor=False):
    """
    Encode a message to travel through a sequence of mixes with a sequence public keys. 
    The maximum size of the final address and the message are 256 bytes and 1000 bytes respectively.
    Returns an 'NHopMixMessage' with four parts: a public key, a list of hmacs (20 bytes each),
    an address ciphertext (256 + 2 bytes) and a message ciphertext (1002 bytes). 

    The implementation of the blinding factor is optional and therefore only activated 
    in the bonus tests. It can be ignored for the standard task.
    If you implement the bonus task make sure to only activate it if use_blinding_factor is True.
    """
    G = EcGroup()
    # assert G.check_point(public_key)
    assert isinstance(address, bytes) and len(address) <= 256
    assert isinstance(message, bytes) and len(message) <= 1000

    # Encode the address and message
    # use those encoded values as the payload you encrypt!
    address_plaintext = pack("!H256s", len(address), address)
    message_plaintext = pack("!H1000s", len(message), message)

    ## Generate a fresh public key
    private_key = G.order().random()
    client_public_key  = private_key * G.generator()

    #TODO ADD CODE HERE
    hmacs = []
    keys_count = len(public_keys)
    
    for i in range(keys_count-1,-1,-1):
	new_macs = []	
	key = public_keys[i]

        encryption_key = private_key * key
        ek = sha512(encryption_key.export()).digest()        
	
        #get coresponding key parts	
        hmac_key = ek[:16]
        address_key = ek[16:32]
        message_key = ek[32:48]
	
        #encrypt for this hop
        iv = b"\x00"*16	
	
	if (i == keys_count-1): # last hop before destination
        	address_cipher = aes_ctr_enc_dec(address_key, iv, address_plaintext)            
        	message_cipher = aes_ctr_enc_dec(message_key, iv, message_plaintext)
	else:
        	address_cipher = aes_ctr_enc_dec(address_key, iv, address_cipher)            
        	message_cipher = aes_ctr_enc_dec(message_key, iv, message_cipher)		

        #calculate mac for this hop        
        h = Hmac(b"sha512", hmac_key)
	
	        		
	if(len(hmacs)>0):	
       	    for i, other_mac in enumerate(hmacs):
                # Ensure the IV is different for each hmac
                iv = pack("H14s", i, b"\x00"*14)
                hmac_enc = aes_ctr_enc_dec(hmac_key, iv, other_mac)
	    	h.update(hmac_enc)	
                new_macs.append(hmac_enc)	

	h.update(address_cipher)
        h.update(message_cipher)
        expected_mac = h.digest()
	expected_mac = expected_mac[:20]	
	
	#print "server hmac_key  : ", hmac_key
	#print "client addr_key  : ", address_key
	#print "server mesg_key  : ", message_key

	#print "client adr_cipher: ", address_cipher[:75]
	#print "client msg_cipher: ", message_cipher[:75]
	
	new_macs.insert(0,expected_mac)
	hmacs = new_macs
	#print "client client_mac: ", expected_mac
		
    return NHopMixMessage(client_public_key, hmacs, address_cipher, message_cipher)



#####################################################
# TASK 4 -- Statistical Disclosure Attack
#           Given a set of anonymized traces
#           the objective is to output an ordered list
#           of likely `friends` of a target user.

import random

def generate_trace(number_of_users, threshold_size, number_of_rounds, targets_friends):
    """ Generate a simulated trace of traffic. """
    target = 0
    others = range(1, number_of_users)
    all_users = range(number_of_users)

    trace = []
    ## Generate traces in which Alice (user 0) is not sending
    for _ in range(number_of_rounds // 2):
        senders = sorted(random.sample( others, threshold_size))
        receivers = sorted(random.sample( all_users, threshold_size))

        trace += [(senders, receivers)]

    ## Generate traces in which Alice (user 0) is sending
    for _ in range(number_of_rounds // 2):
        senders = sorted([0] + random.sample( others, threshold_size-1))
        # Alice sends to a friend
        friend = random.choice(targets_friends)
        receivers = sorted([friend] + random.sample( all_users, threshold_size-1))

        trace += [(senders, receivers)]

    random.shuffle(trace)
    return trace


from collections import Counter

def analyze_trace(trace, target_number_of_friends, target=0):
    """ 
    Given a trace of traffic, and a given number of friends, 
    return the list of receiver identifiers that are the most likely 
    friends of the target.
    """
    
    #TODO ADD CODE HERE
    
    suspect_list = []
    #find the rounds where alice sent messages
    for round in trace:			
    	if (target in round[0]):
		#remember all receivers in this round
		for r in round[1]:		
			suspect_list.append(r)
	
    #find whicch users appear most often on the "suspect list"		
    counter = Counter(suspect_list)
    common = counter.most_common(target_number_of_friends)
    friends = []	
    for pair in common:
	friends.append(pair[0])		
	
    return friends











