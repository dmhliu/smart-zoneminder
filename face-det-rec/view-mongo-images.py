"""
This program will fetch documents from the Mongodb collection written to by zm-s3-uploader.js.
Then face detection / recognition can be applied by stepping through the stored images.
This is useful to tune the face detection / recognition parameters. 

Copyright (c) 2019 Lindo St. Angel
"""

import face_recognition
import argparse
import pickle
import cv2
import json
from pymongo import MongoClient
from bson import json_util

# Where to save images and metadata of examined data. 
SAVE_PATH = '/home/lindo/develop/smart-zoneminder/face-det-rec/saved_images'

# Path to known face encodings in python pickle serialization format.
# The pickle file needs to be generated by the 'encode_faces.py' program first.
KNOWN_FACE_ENCODINGS_PATH = '/home/lindo/develop/smart-zoneminder/face-det-rec/encodings.pickle'

# Face comparision tolerance.
# A lower value causes stricter compares which may reduce false positives.
# See https://github.com/ageitgey/face_recognition/wiki/Face-Recognition-Accuracy-Problems.
COMPARE_FACES_TOLERANCE = 0.57

# Face detection model to use. Can be either 'cnn' or 'hog'
FACE_DET_MODEL = 'cnn'

# How many times to re-sample the face when calculating face encoding.
NUM_JITTERS = 100

# url of mongodb database that zm-s3-upload.js uses.
MONGO_URL = 'mongodb://zmuser:zmpass@localhost:27017/?authSource=admin'

# Number of documents to fetch from the mongodb database.
NUM_ALARMS = 2000

# Object detection confidence threshold.
IMAGE_MIN_CONFIDENCE = 60 

# Set to True to see most recent alarms first.
IMAGE_DECENDING_ORDER = False

# Key codes on my system for cv2.waitKeyEx().
ESC_KEY = 1048603
RIGHT_ARROW_KEY = 1113939
LEFT_ARROW_KEY = 1113937
UP_ARROW_KEY = 1113938
DOWN_ARROW_KEY = 1113940
SPACE_KEY = 1048608
LOWER_CASE_Q_KEY = 1048689
LOWER_CASE_S_KEY = 1048691

# Load the known faces and embeddings.
with open(KNOWN_FACE_ENCODINGS_PATH, 'rb') as fp:
    data = pickle.load(fp)

client = MongoClient(MONGO_URL)

alarms = []

# Query database for person objects.
# Return documents in descending order and limit.
with client:
	db = client.zm
	alarms = list(
		db.alarms.find(
			{'labels.Labels.Name' : 'person'}
		).sort([('_id', -1)]).limit(NUM_ALARMS)
	)

idx = 0

# Since alarms are in decending order by default reverse list to see earlist alarms first.
if not IMAGE_DECENDING_ORDER:
	alarms.reverse()

# Create a window that can be resized by the user.
# TODO: figure out why I cannot resize window using the mouse
cv2.namedWindow('face detection results', cv2.WINDOW_NORMAL)

while True:
	alarm = alarms[idx]

	print(alarm)

	img = cv2.imread(alarm['image'])
	if img is None:
		print('Alarm image not found...skipping.')
		idx += 1
		if idx > len(alarms) - 1:
			print('Reached end of alarm images...exiting.')
			break
		continue

	labels = alarm['labels']

	# Find all roi's in image, then look for faces in the rois, then show faces on the image.
	for object in labels['Labels']:
		if object['Name'] == 'person' and object['Confidence'] > IMAGE_MIN_CONFIDENCE:
			print('Found person object...')
			# (0, 0) is the top left point of the image.
			# (x1, y1) are the top left roi coordinates.
			# (x2, y2) are the bottom right roi coordinates.
			y2 = int(object['Box']['ymin'])
			x1 = int(object['Box']['xmin'])
			y1 = int(object['Box']['ymax'])
			x2 = int(object['Box']['xmax'])

			# draw the roi and its label on the image
			cv2.rectangle(img, (x1, y1), (x2, y2), (255,0,0), 2)
			cv2.putText(img, 'person', (x1, y2 - 15), cv2.FONT_HERSHEY_SIMPLEX,
				0.75, (0, 255, 0), 2)
			#cv2.imshow('roi', img)
			#cv2.waitKey(0)

			roi = img[y2:y1, x1:x2, :]
			if roi.size == 0:
				continue
			#cv2.imshow('roi', roi)
			#cv2.waitKey(0)

			# Covert from cv2 to rgb format.
			rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)

			# detect the (x, y)-coordinates of the bounding boxes corresponding
			# to each face in the input image, then compute the facial embeddings for each face
			# Do not increase upsample. System will crash from out of memory.
			box = face_recognition.face_locations(rgb, number_of_times_to_upsample=1,
				model=FACE_DET_MODEL)

			encodings = face_recognition.face_encodings(rgb, box, NUM_JITTERS)

			# initialize the list of names for each face detected
			names = []

			# loop over the facial embeddings
			for encoding in encodings:
				# attempt to match each face in the input image to our known encodings
				matches = face_recognition.compare_faces(data['encodings'],
					encoding, COMPARE_FACES_TOLERANCE)
				name = 'Unknown'

				# check to see if we have found a match
				if True in matches:
					# find the indexes of all matched faces then initialize a
					# dictionary to count the total number of times each face
					# was matched
					matchedIdxs = [i for (i, b) in enumerate(matches) if b]
					counts = {}

					# loop over the matched indexes and maintain a count for
					# each recognized face face
					for i in matchedIdxs:
						name = data['names'][i]
						counts[name] = counts.get(name, 0) + 1

					# determine the recognized face with the largest number of
					# votes (note: in the event of an unlikely tie Python will
					# select first entry in the dictionary)
					name = max(counts, key=counts.get)

					print('named {}'.format(name))

				# update the list of names
				names.append(name)

			# loop over the recognized faces
			for ((top, right, bottom, left), name) in zip(box, names):
				#print('face box top {} right {} bottom {} left {}'.format(top, right, bottom, left))
				face_box_width = right - left
				face_box_height = bottom - top
				print('face box width {} height {}'.format(face_box_width, face_box_height))
				# draw the predicted face box and put name on the image
				cv2.rectangle(img, (left + x1, top + y2), (right + x1, bottom + y2), (0, 255, 0), 2)
				y = top + y2 - 15 if top + y2 - 15 > 15 else top + y2 + 15
				cv2.putText(img, name, (left + x1, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
				# put originally predicted name on image as well if it differs from new predicted name
				# if different name it will be shown in red text
				if name != object['Face']:
					y = bottom + y2 + 15 if bottom + y2 + 15 > 15 else bottom + y2 - 15
					cv2.putText(img, object['Face'], (left + x1, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)

	cv2.imshow('face detection results', img)

	key = cv2.waitKeyEx()
	#print('key press {}'.format(key))
	if key == LOWER_CASE_Q_KEY or key == ESC_KEY: # exit program
		break
	if key == LOWER_CASE_S_KEY: # save current image and metadata
		obj_id_str = str(alarm['_id'])
		print('Saving current alarm with id {}.'.format(obj_id_str))
		cv2.imwrite(SAVE_PATH + '/' + obj_id_str + '.jpg', img)
		json_dumps = json.dumps(alarm, default=json_util.default)
		with open(SAVE_PATH + '/' + obj_id_str + '.json', 'w') as outfile:
			json.dump(json_dumps, outfile)
	elif key == LEFT_ARROW_KEY or key == DOWN_ARROW_KEY: # go back
		idx -= 1
	elif key == SPACE_KEY or key == RIGHT_ARROW_KEY or key == UP_ARROW_KEY: # advance
		idx += 1
		if idx > len(alarms) - 1:
			print('Reached end of alarm images...exiting.')
			break

cv2.destroyAllWindows()