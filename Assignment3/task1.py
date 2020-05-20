import os
import sys
import csv
import json
import time
import random
import pyspark
from operator import add
from pprint import pprint
from pyspark import SparkContext
from itertools import combinations

ticTime = time.time()

## Initialising the SparkContext.
sc = SparkContext('local[*]', 'Task1')
sc.setLogLevel("ERROR")

## Defining the path to the data. 
dataSetPath = sys.argv[1]

## Output file path.
outfilePath = sys.argv[2]

## Loading the raw data.
rawData = sc.textFile(dataSetPath)

## Filter out lines.
header = rawData.first()

## Loading the CSV data.
yelpData = rawData.filter(lambda line: line != header).map(lambda f: f.split(","))

## Create a mapping of the form: {bi : [ui, ... , uk]}.
ratedBusinessUsers = yelpData.map(lambda f : (f[1], f[0])).groupByKey().mapValues(set)

## Create a list of the total unique users in the dataset.
uniqueUsers = yelpData.map(lambda f : f[0]).distinct().sortBy(lambda f : f[0]).collect()

## Create a user-index structure based dictionary.
userIndexDict = dict(zip(uniqueUsers, range(len(uniqueUsers))))

## Total number of unique users.
numUsersTotal = len(uniqueUsers)

## Functions for generating prime numbers.
def isPrime(num):
	for m in range(2, int(num ** 0.5) + 1):
	    if not num % m:
	        return False
	return True

def findPrime(num):
    for n in range(num + 1, num + 10000):
        if isPrime(n): return n

## Function to generate the random hash functions for simulating the permutations.
def hashFunction(numHashFunctions, m):

	## Generate random values for a and b.
	a = random.sample(range(1, m), numHashFunctions)
	b = random.sample(range(1, m), numHashFunctions)
	
	## Generate random prime numbers greater than m.
	p = [findPrime(i) for i in random.sample(range(m, m + 10000), numHashFunctions)]

	## Return the hashed value.
	return {'a' : a, 'b' : b, 'p' : p}

## Function to compute the signature matrix from the characteristic matrix.
def computeSignatureMatrix(userIndexDict, ratedBusinessUsersChunk, numHashFunctions, numUsers, hashParams):

	## Convert the input chunk to a list.
	ratedBusinessUsersChunk = list(ratedBusinessUsersChunk)

	## Extracting the key-value pairs.
	currBusiness, userList = ratedBusinessUsersChunk[0], ratedBusinessUsersChunk[1]

	## Initialise a signature matrix.
	sigMat = [float('inf') for i in range(numHashFunctions)]

	## Loop over each user for the current business.
	for currUser in userList:

		## Extract the index of the current user.
		userIndex = userIndexDict[currUser]  

		## Compute the hash function value for all the hash functions.
		for i in range(numHashFunctions):
			hashVal = (((hashParams['a'][i]*userIndex + hashParams['b'][i])%hashParams['p'][i])%numUsers)

			## Update the value if required.
			if (hashVal < sigMat[i]):
				sigMat[i] = hashVal

	return sigMat

## Defining the number of hash-functions.
numHashFunctions = 150

## Obtaining the hashing parameters.
hashParams = hashFunction(numHashFunctions, numUsersTotal)

## Compute the signature matrix.
signatureMatrix = ratedBusinessUsers.map(lambda currChunk : (currChunk[0], computeSignatureMatrix(userIndexDict, currChunk, numHashFunctions, numUsersTotal, hashParams)))

## Split the signature matrix to individual bands.
numBands = 75
numRowsPerBand = numHashFunctions // numBands

## Function to split the signature matrix into individual bands.
def splitSigMatToBands(sigMatChunk, numBands, numRowsPerBand):

	## Convert the input chunk to a list.
	sigMatChunk = list(sigMatChunk)
	
	## Extracting the key-value pairs.
	currBusiness, minHashValues = sigMatChunk[0], sigMatChunk[1]

	## List to hold the bands for the current business.
	bandsList = []

	## Counter for keeping track of the band number.
	bandNum = 0

	## Splitting up into equal sized bands.
	for i in range(0, len(minHashValues), numRowsPerBand):

		## Obtain the band.
		currBand = tuple(minHashValues[i : i + numRowsPerBand])

		## Add the entry to the bandsList.
		bandsList.append(((bandNum, currBand), currBusiness))

		## Update the band number.
		bandNum += 1

	return bandsList

# Obtain the list of business ID's which hash to the same bucket across all bands.
bandedSigMat = signatureMatrix.flatMap(lambda currChunk : splitSigMatToBands(currChunk, numBands, numRowsPerBand)).groupByKey().mapValues(list).map(lambda f: list(f[1])).filter(lambda f : len(f) > 1)

## Function to generate the set of candidate pairs.
def generateCandidatePairs(businessIDListChunk):

	## Convert the input chunk to a list.
	businessIDListChunk = list(businessIDListChunk)	
	
	## Return all the possible pairs.
	return combinations(businessIDListChunk, 2)

## Obtain the set of candidate pairs.
candidatePairs = bandedSigMat.flatMap(lambda currChunk : generateCandidatePairs(currChunk)).distinct()

## Defining a function to compute the Jaccard Similarity.
def computeJC(candidatePair, ratedBusinessUsers):

	## Obtain the list of users for the businesses in the candidate.
	businessList1 = ratedBusinessUsers[candidatePair[0]]
	businessList2 = ratedBusinessUsers[candidatePair[1]]

	## Compute the intersection and union.
	setIntersection = businessList1 & businessList2
	setUnion = businessList1 | businessList2

	candidatePair = tuple(sorted(candidatePair))

	return candidatePair, (len(setIntersection) / len(setUnion))

## Collect the ratedBusinessUsers RDD.
ratedBusinessUsers = {i: j for i, j in ratedBusinessUsers.collect()}

## Computing the Jaccard Similarity for the candidate pairs.
similarPairs = candidatePairs.map(lambda currPair : computeJC(currPair, ratedBusinessUsers)).filter(lambda f : f[1] >= 0.5).collect()
similarPairs.sort()

fout = open(outfilePath, mode = 'w')
fwriter = csv.writer(fout, delimiter = ',', quoting = csv.QUOTE_MINIMAL)
fwriter.writerow(['business_id_1', ' business_id_2', ' similarity'])
for pair in similarPairs:
    fwriter.writerow([str(pair[0][0]), str(pair[0][1]), pair[1]])
fout.close()


tockTime = time.time()
print(tockTime - ticTime)