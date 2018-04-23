import matplotlib

matplotlib.use('Agg')

import hdhp
import json
import numpy as np
import os
import timeit
from datetime import datetime
import random
import operator
import codecs
# from nltk.corpus import stopwords
import re


def create_mongodb_connection_info(db_server, db_name, db_user, db_password):
    """
    This function returns the mongoDB connection info.
    :param db_server: address of mongoDB server
    :param db_name: mongoDB database name
    :param db_user: mongoDB user
    :param db_password: user's password
    :return: mongoDB connection info.
    """
    db_connection = "mongodb://" + db_user + ":" + db_password + "@" + db_server + "/" + db_name
    return db_connection

def metadata_to_database(metadata_file_path, db_connection_info, metadata_collection):
    """
    This function gets the metadata of all papers as a xml file, and inserts them into a 'MongoDB' database.
    :param metadata_file_path: The address of the metadata file (xml file).
    :param db_connection_info: database connection information (server, username, password)
    :return: Nothing.
    """

    from pymongo import MongoClient
    import xml

    client = MongoClient(db_connection_info)  # Connect to the MongoDB
    db = client.arXiv  # Gets the related database

    for event, elem in xml.etree.ElementTree.iterparse(metadata_file_path):

        if elem.tag == "metadata":
            mongoDB_document = {}
            for child in elem.iter():  # Build a document for each record's metadata
                current_tag = child.tag
                if current_tag == "metadata" or current_tag == "{http://www.openarchives.org/OAI/2.0/oai_dc/}dc":
                    continue
                current_tag = current_tag.replace("{http://purl.org/dc/elements/1.1/}", "").strip()
                child_text = child.text
                if child_text is None:
                    continue
                child_text = child_text.strip().replace("\n", " ")
                if current_tag == "type" or current_tag == "title" or current_tag == "language":
                    mongoDB_document[current_tag] = child_text
                else:
                    if current_tag in mongoDB_document:
                        mongoDB_document[current_tag] = mongoDB_document.get(current_tag) + [child_text]
                    else:
                        mongoDB_document[current_tag] = [child_text]

            db[metadata_collection].insert_one(mongoDB_document)  # Insert the document in to the database
            elem.clear()
    client.close()


def modify_CS_Papers(db_connection_info, old_file_path, new_file_path, metadata_collection):
    from pymongo import MongoClient

    stopwords_file_path = "stopwords.txt"
    with open(stopwords_file_path) as stopwords_file:
        stopwords = stopwords_file.readlines()

    for i in range(len(stopwords)):
        stopwords[i] = stopwords[i].strip()

    print("stopwords: " + str(len(stopwords)))

    client = MongoClient(db_connection_info)  # Connect to the MongoDB
    db = client.arXiv  # Gets the related database

    old_data = json.load(open(old_file_path))
    new_data = {}

    for identifier in old_data:
        paper = old_data.get(identifier)
        document = db[metadata_collection].find_one({'identifier': {'$in': [identifier]}})
        new_abstract = document['description'][0]

        paper_abstract = new_abstract.lower()
        paper_abstract = re.sub("{|}|(|)|=|;|,|\?|\d+", "", paper_abstract)
        paper_abstract = re.sub("(|)|:|\d+|\.", " ", paper_abstract)
        paper_abstract = ' '.join(
            [word.strip() for word in paper_abstract.split() if word not in stopwords and len(word) > 1])
        paper["abstract"] = paper_abstract

        paper_title = document["title"].lower()
        paper_title = re.sub("{|}|;|,|\?|\.", "", paper_title)
        paper_title = re.sub(":|;|,|\?|\.", " ", paper_title)
        paper_title = ' '.join([word.strip() for word in paper_title.split() if word not in stopwords])
        paper["title"] = paper_title

        citations = paper['citations']
        new_citations = []

        for index in range(len(citations)):

            citation = citations[index]
            author = citation['author']
            new_author = []

            for item in author:
                item = item.strip()
                if len(item) < 2:
                    continue
                if 'et al.' in item:
                    item = item[0: item.index('et al.')]
                if 'title' in item:
                    continue
                if item.startswith(','):
                    continue

                if '{' in item and len(item.split(' ')) > 3:
                    item = item[0: item.index('{')]
                if '$' in item:
                    item = item[0: item.index('$')]
                if ',' in item:
                    splitted = item.split(',')
                    if len(splitted) > 1:
                        item = splitted[1].strip() + ' ' + splitted[0].strip()
                    else:
                        item = splitted[0]
                if ':' in item:
                    item = item[0: item.index(':')]

                splitted_item = item.split(' ')

                new_item = ''

                for temp in splitted_item:
                    new_item += temp.strip() + '#'

                new_item = new_item[0:-1]
                new_author.append(new_item)
                citation['author'] = new_author

                new_citations.append(citation)

            paper['citations'] = new_citations
        new_data[identifier] = paper

    json_file = open(new_file_path, 'w')
    json.dump(new_data, json_file, indent=0)
    json_file.close()
    client.close()


def jsonFileToEvents(targetFile):
    start = timeit.default_timer()
    # names_to_ids = maps_authors_to_ids(targetFile)

    events = list()
    json_data = json.load(open(targetFile))
    times = {}

    for identifier in json_data:
        paper = json_data.get(identifier)
        times[identifier] = paper["time"]

    sorted_times = sorted(times.items(), key=operator.itemgetter(1))
    counter = 0
    unique_authors = {}

    for item in sorted_times:
        identifier = item[0]
        paper = json_data.get(identifier)

        authors_vocabs = ''

        for citation in paper["citations"]:
            authors = citation["author"]

            for author in authors:
                authors_vocabs += author.strip() + ' '

        authors = paper['author']
        authors_ids = []

        for author in authors:
            if author not in unique_authors:
                unique_authors[author] = counter
                authors_ids.append(counter)
                counter += 1
            else:
                authors_ids.append(unique_authors[author])

        # vocabularies = {"docs": paper["abstract"], "auths": authors_vocabs.strip()}
        vocabularies = {"docs": paper["title"], "auths": authors_vocabs.strip()}

        paper["author_ids"] = authors_ids
        event = (paper["time"], vocabularies, paper["author_ids"], [])
        events.append(event)

    print("Number of events: " + str(len(events)))
    print("Execution Time: " + str(timeit.default_timer() - start))
    return events


def find_first_date(targetFile):
    json_data = json.load(open(targetFile))
    first_date = datetime.now()

    for identifier in json_data:
        paper = json_data.get(identifier)
        paper_time = datetime.strptime(paper["date"][0], '%Y-%m-%d')

        if paper_time < first_date:
            first_date = paper_time

    print(str(first_date))


def num_unique_authors(targetFile):
    json_data = json.load(open(targetFile))
    unique_authors = []

    for identifier in json_data:
        paper = json_data.get(identifier)
        for author in paper["author"]:
            unique_authors.append(author.strip())

    print("Number of all authors: " + str(len(unique_authors)))
    print("Number of unique authors: " + str(len(set(unique_authors))))


def get_number_of_authors(events):
    unique_authors = []

    for tuple in events:
        unique_authors += tuple[2]

    return len(set(unique_authors))


def maps_authors_to_ids(targetFile):
    json_data = json.load(open(targetFile))
    stopwords_file_path = "stopwords.txt"

    with open(stopwords_file_path) as stopwords_file:
        stopwords = stopwords_file.readlines()

    for i in range(len(stopwords)):
        stopwords[i] = stopwords[i].strip()

    new_file = "/NL/publications-corpus/work/new_CS_arXiv_real_data.json"

    base_time = datetime.strptime('1996-06-03', '%Y-%m-%d')


    counter = 0
    names_to_ids = {}
    new_json_data = {}

    for identifier in json_data:
        paper = json_data.get(identifier)

        authors = paper["author"]
        for author in authors:
            if author.strip() not in names_to_ids:
                counter += 1
                names_to_ids[author.strip()] = counter

    for identifier in json_data:
        paper = json_data.get(identifier)

        authors = paper["author"]
        ids = []
        for author in authors:
            ids.append(names_to_ids.get(author.strip()))
        paper_abstract = paper["abstract"].lower()
        paper_abstract = ' '.join([word for word in paper_abstract.split() if word not in stopwords])
        paper_abstract = re.sub(":|;|,|\?|\.", "", paper_abstract)
        paper["abstract"] = paper_abstract

        paper_title = paper["title"].lower()
        paper_title = ' '.join([word for word in paper_title.split() if word not in stopwords])
        paper_title = re.sub(":|;|,|\?|\.", "", paper_title)
        paper["title"] = paper_title

        paper['author_ids'] = ids

        paper_time = datetime.strptime(paper["date"][0], '%Y-%m-%d')
        time_diff = paper_time - base_time
        time = time_diff.total_seconds() / (3600 * 24) + random.uniform(0, 1)
        paper['time'] = time
        new_json_data[identifier] = paper

    with open(new_file, 'w') as output_file:
        json.dump(new_json_data, output_file, indent=1)
    print("Number of unique ids: " + str(len(names_to_ids)))
    return names_to_ids


def authors_info(dataset_file_path):
    with open(dataset_file_path) as input_file:

        json_data = json.load(input_file)
        unique_authors = {}
        papers_per_user = {}
        events_per_user = {}
        counter = 0

        for identifier in json_data:

            paper = json_data.get(identifier)
            authors = paper["author"]

            for author in authors:
                if author not in unique_authors:
                    unique_authors[author] = counter
                    counter += 1

                if unique_authors[author] not in papers_per_user:
                    papers_per_user[unique_authors[author]] = 1
                else:
                    papers_per_user[unique_authors[author]] += 1

            if unique_authors.get(authors[0]) not in events_per_user:
                events_per_user[unique_authors.get(authors[0])] = 1
            else:
                events_per_user[unique_authors.get(authors[0])] += 1

        sorted_num_events = sorted(events_per_user.items(), key=operator.itemgetter(1))

        with open("num_events_per_user.txt", 'w') as out_file:

            for author_id in sorted_num_events:
                out_file.write(str(author_id) + '\t' + str(sorted_num_events.get(author_id)) + '\n')

        sorted_num_papers = sorted(papers_per_user.items(), key=operator.itemgetter(1))
        with open("num_papers_per_author.txt", 'w') as out_file:

            for author_id in sorted_num_papers:
                out_file.write(str(author_id) + '\t' + str(sorted_num_papers.get(author_id)) + '\n')

        print("Number of unique authors: " + str(len(unique_authors)))


def infer(rawEvents, indices, num_particles, alpha_0, mu_0, omega, use_cousers=False):
    start = timeit.default_timer()

    types = ["docs", "auths"]

    # num_patterns = 10
    # num_users = 64442 # Number of unique authors
    num_users = get_number_of_authors(rawEvents)  # Number of unique authors
    print("Num of authors: " + str(num_users))

    # # Inference
    types = [types[i] for i in indices]

    events = list()

    if use_cousers:
        for event in rawEvents:
            events.append((event[0], {t: event[1][t] for t in types}, event[2], event[3]))
    else:
        for event in rawEvents:
            events.append((event[0], {t: event[1][t] for t in types}, [event[2][0]], event[3]))

    particle, norms = hdhp.infer(events,
                                 alpha_0,
                                 mu_0,
                                 types,
                                 omega=omega,
                                 beta=1,
                                 threads=1,
                                 num_particles=num_particles,
                                 keep_alpha_history=True,
                                 seed=512)

    print("Execution time of calling infer function: " + str(timeit.default_timer() - start))
    start = timeit.default_timer()

    inf_process = particle.to_process()
    print("Convert to process - time: " + str(timeit.default_timer() - start))

    return inf_process


def main():
    real_data_file_path = "../Real_Dataset/new_CS_arXiv_real_data.json"
    # priors to control the time dynamics of the events
    alpha_0 = (4.0, 0.5)  # prior for excitation
    mu_0 = (8, 0.25)  # prior for base intensity
    omega = 5  # decay kernel
    num_particles = 10

    db_user = ""
    db_password = ""
    db_name = ""
    db_server = ""
    db_connection_info = create_mongodb_connection_info(db_server, db_name, db_user, db_password)
    metadata_collection = ""
    metadata_file_path = ""

    old_file_path = "/NL/publications-corpus/work/new_CS_arXiv_real_data.json"
    new_file_path = "/NL/publications-corpus/work/modified_CS_arXiv_real_data.json"
    metadata_to_database(metadata_file_path, db_connection_info, metadata_collection)

    modify_CS_Papers(db_connection_info, old_file_path, new_file_path, metadata_collection)

    authors_info(new_file_path)


    events = jsonFileToEvents(real_data_file_path)
    number_of_events = 10
    print("Number of events: " + str(number_of_events))

    cases = {1: ([0], False),
             2: ([0, 1], False),
             3: ([0, 1], True)}

    for case in [3, 2, 1]:
        print "Case: {0}".format(case)
        indices, use_cousers = cases[case]

        print("Start inferring.....")
        infHDHP = infer(events[: number_of_events], indices, num_particles, alpha_0, mu_0, omega,
                        use_cousers=use_cousers)
        print("End inferring...")

        with open("real_data_results/" + "Case{0}".format(case) + "/title_base_rates_" + str(
                number_of_events) + ".tsv", "w") as output_file:
            for key in infHDHP.mu_per_user:
                output_file.write("\t".join([str(key), str(infHDHP.mu_per_user[key])]) + "\n")

        with open("real_data_results/" + "Case{0}".format(case) + "/title_est_time_kernels_" + str(
                number_of_events) + ".tsv", "w") as output_file:
            for key in infHDHP.time_kernels:
                output_file.write("\t".join([str(key), str(infHDHP.time_kernels[key])]) + "\n")

        clusters = infHDHP.show_annotated_events()
        with codecs.open("real_data_results/" + "Case{0}".format(case) + "/title_annotated_events_" + str(
                number_of_events) + ".txt", "w", encoding="utf-8") as output_file:
            output_file.write(clusters)

        dist = infHDHP.show_pattern_content()
        with codecs.open("real_data_results/" + "Case{0}".format(case) + "/title_pattern_content_" + str(
                number_of_events) + ".txt", "w", encoding="utf-8") as output_file:
            output_file.write(dist)
        # print("show_pattern_content return: \n" + dist)

        predLabs = [e[1] for e in infHDHP.annotatedEventsIter()]

        with open("real_data_results/" + "Case{0}".format(case) + "/title_patterns_" + str(number_of_events) + ".tsv",
                  "w") as output_file:
            for i in xrange(len(predLabs)):
                output_file.write(str(predLabs[i]) + "\n")

                # for key in infHDHP.time_history_per_user:
                #     print(str(key) + " : " + str(infHDHP.time_history_per_user[key]))

                # for key in infHDHP.pattern_popularity:
                #     print(key + " : " + str(infHDHP.pattern_popularity[key]))


if __name__ == "__main__":
    main()