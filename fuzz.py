import os.path

import mechanicalsoup
from urllib.parse import urlparse, urljoin, parse_qs, ParseResult
import argparse

def discover_init(host_url: str, visited_urls: dict, dvwa_auth=False, common_words=[], extensions=[]):
    # Init MechanicalSoup with host url
    browser = mechanicalsoup.StatefulBrowser(user_agent='MechanicalSoup')
    # TODO: Make sure this doesnt break anything
    try:
        host_url = host_url + "/" if not host_url.endswith("/") else host_url
        print("Visiting URL '{}'...".format(host_url))
        browser.open(host_url)
    except Exception as e:
        print("Failed to connect to host url '{}': {}".format(host_url, e))
        return

    # Visited url data storage
    if (visited_urls.get(host_url) == None):
        visited_urls[host_url] = {}
    else:
        print("Revisited URL '{}', was this intentional?".format(host_url))

    # DVWA Custom Auth
    if (dvwa_auth):
        DVWA_custom_auth(host_url, browser)

    discover_pages(host_url, browser, visited_urls, common_words, extensions)

    # Print list of visited urls (if any)
    if (len(visited_urls) > 0):
        print("Visited urls: ")
        for url in visited_urls:
            url_obj = visited_urls[url]
            if (len(url_obj.get("inputs")) > 0):
                print("'{}': Inputs: {}".format(url, url_obj["inputs"]))
            else:
                print("'{}'".format(url))
        print("***********************************************************************")

def discover_pages(host_url: str, browser: mechanicalsoup.StatefulBrowser, visited_urls: {str: dict}, common_words=[], extensions=[]):
    # TODO: Ensure do not logout by accident (visit logout page / click button)
    """
    Discover sub-pages of a given host URL, avoiding external domains and finding possible inputs.

    Args:
        host_url (str): The URL to explore
        visited_urls (set): Set to keep track of visited URLs to avoid duplicates
        common_words (list): List of common words for url guessing
        extensions (list): List of extensions for url guessing
    """
    try:
        host_url = host_url + "/" if not host_url.endswith("/") and not host_url.endswith("php") and not host_url.endswith(".") else host_url

        browser.open(host_url)

        # Parse the host URL to extract domain/hostname
        parsed_host_url = urlparse(host_url)

        # Discover inputs on the page
        inputs = discover_inputs(parsed_host_url, browser)

        # Init dict struct if needed
        if (visited_urls.get(host_url).get("inputs") == None):
            visited_urls.get(host_url)["inputs"] = {}

        # Insert input data
        if(len(inputs["qip"]) > 0):
            visited_urls[host_url]["inputs"]["query"] = inputs["qip"]
        if (len(inputs["fip"]) > 0):
            visited_urls[host_url]["inputs"]["forms"] = inputs["fip"]
        if (len(inputs["cip"]) > 0):
            visited_urls[host_url]["inputs"]["cookies"] = inputs["cip"]

        # Find all links on the page
        link_objects = browser.page.find_all('a', href=True)
        # print("Link objects found: '{}'".format([l.get("href") for l in link_objects]))
        print("{} Link objects found".format(len(link_objects)))

        print("***********************************************************************")

        # Crawl sub-pages (recursively calls discover and fills visited_urls
        crawl_links(host_url, parsed_host_url, visited_urls, browser, link_objects, common_words, extensions)
    except Exception as e:
        print("An error occurred accessing '{}': {}".format(host_url, e))


def crawl_links(base_url: str, parsed_host_url: ParseResult, visited_urls: dict, browser: mechanicalsoup.StatefulBrowser, link_objects: [], common_words: [], extensions: []):
    """
    Crawl pages stemming from the given base url via direct page discovery and guessing. Recurses on discover_pages.

    Args:
        base_url (str): Base url string to crawl
        base_url (str): Base url to crawl
        parsed_host_url (ParseResult): Parsed base url object
        browser (mechanicalsoup.StatefulBrowser): Browser object, used to perform page discovery
        link_objects (list): List of link objects to crawl
        common_words (list): List of common words to guess with
        extensions (list): List of extensions to guess with
        visited_urls (set): Set of visited urls
    """

    if(base_url.endswith(".php")):
        return

    # Guess at pages then add only valid results to link_objects for crawling
    link_objects += guess_pages(base_url, browser, common_words, extensions)

    # Iterate over found links
    for lo in link_objects:
        # Extract URL from link object
        href = lo['href']
        while(href.startswith(".") or href.startswith("/")):
            href = href[1:]
        href = href + "/" if not href.endswith("/") and not href.endswith("php") else href
        href_obj = urlparse(href)
        if(href_obj.netloc != "" and href_obj.netloc != parsed_host_url.netloc):
            continue
        path = href_obj.path
        path = "" if path == "/" else path
        path = path[1:] if path.startswith("/") else path

        query = href_obj.query
        query = "?" + query if query != "" else query

        link_url = base_url + path + query

        # Parse the link URL
        parsed_link_url = urlparse(link_url)

        # Check if the absolute URL is within the same domain and has not been previously visited
        if (parsed_host_url.netloc == parsed_link_url.netloc and link_url not in visited_urls and not parsed_link_url.path.endswith("logout.php")):
            if(browser.get(link_url).status_code == 200):
                print("Visiting URL '{}'...".format(link_url))

                # Recursively explore sub-pages
                visited_urls[link_url] = {}
                discover_pages(link_url, browser, visited_urls, common_words, extensions)


def guess_pages(base_url: str, browser: mechanicalsoup.StatefulBrowser, common_words: [], extensions: []):
    """
    Guess at possible urls that stem from the given base_url and return all valid combinations. To
    be considered valid, the new url must return a 200 response to a GET request.
    Args:
        base_url (str): Base url string
        browser (mechanicalsoup.StatefulBrowser): Browser object, used to perform page discovery
        common_words (list): List of common words to guess with
        extensions (list): List of extensions to guess with

    Returns: List of found link objects (relative link held in 'href' property)

    """
    link_objects = []

    # If no common words provided, skip guessing
    if(common_words is None):
        return link_objects

    # Iterate over common words
    for cw in common_words:
        # Guess /common_word
        full_guess = base_url + cw
        if (browser.get(full_guess).status_code == 200):
            link_objects.append({'href': cw})
            print("Valid guess found: '{}'".format(full_guess))

        # If no extensions provided, skip extension guesses
        if(extensions is None):
            continue

        # Iterate over extensions
        for ext in extensions:
            # Guess /common_word.extension
            cw_ext_guess = "{}.{}".format(cw, ext)
            full_guess = base_url + cw_ext_guess
            if(browser.get(full_guess).status_code == 200):
                link_objects.append({'href': cw_ext_guess})
                print("Valid guess found: '{}'".format(full_guess))

    # Return list of found links (formatted into objects with an 'href' attribute)
    return link_objects


def discover_inputs(parsed_url: ParseResult, browser: mechanicalsoup.StatefulBrowser):
    """
    Parses the current page (selected in the browser object) for any inputs that can be found.

    Args:
        parsed_url (ParseResult): Parsed url object of the current page.
        browser (mechanicalsoup.StatefulBrowser): Browser object, used to perform input discovery

    Returns:
        Discovered inputs from the query string, any forms, and cookies {"qip": {<input name>: <list of possible values>}}
    """
    # Find and print possible input parameters on the current page
    query_input_params = {}
    form_input_params = {}
    cookie_input_params = {}

    # Discover parameter inputs from parsed URL
    query_params = parse_qs(parsed_url.query)
    for param_name, param_values in query_params.items():
        query_input_params[param_name] = param_values

    # Find input elements in forms
    form_inputs = browser.page.find_all('input', {'name': True})
    for fi in form_inputs:
        form_input_params[fi['name']] = []

    # Discover cookies
    cookies = browser.get_cookiejar().items()
    for cookie_name, cookie_value in cookies:
        cookie_input_params[cookie_name] = cookie_value

    # Print info about any discovered inputs
    if(len(query_input_params) > 0):
        print("Possible query input parameters: [{}]".format(', '.join("Name: '{}', Values: {}".format(key, val) for key, val in query_input_params.items())))
    else:
        print("No possible query input parameters found.")
    if (len(form_input_params) > 0):
        print("Possible form input parameters: [{}]".format(', '.join("Name: '{}', Values: {}".format(key, val) for key, val in form_input_params.items())))
    else:
        print("No possible form input parameters found.")
    if (len(cookie_input_params) > 0):
        print("Possible cookie input parameters: [{}]".format(', '.join("Name: '{}', Value: {}".format(key, val) for key, val in cookie_input_params.items())))
    else:
        print("No possible cookie input parameters found.")

    return {"qip": query_input_params, "fip": form_input_params, "cip": cookie_input_params}


def DVWA_custom_auth(host_url: str, browser: mechanicalsoup.StatefulBrowser):
    """
    Executes a custom auth sequence meant for the DVWA site. This method performs all required
    steps to initialize, sign in, and set the security to low without user interaction.

    Args:
        host_url (str): base DVWA url
        browser (mechanicalsoup.StatefulBrowser): Browser object, used to perform auth sequence
    """
    print("Starting DVWA Custom Auth...")
    # Visit setup page, init/reset db (by submitting)
    browser.open(host_url + "/setup.php")
    browser.select_form()
    browser.submit_selected()

    # Return to base url (redirects to login page)
    browser.open(host_url)

    # Fill out login form then submit
    browser.select_form()
    browser["username"] = "admin"
    browser["password"] = "password"
    response = browser.submit_selected()

    # Print erroneous login responses
    if(response.status_code != 200):
        print("DVWA Login Response: {}: {}".format(response.status_code, response.reason))

    # Visit security page, set security to Low, then submit form and return to homepage
    browser.open(host_url + "/security.php")
    browser.select_form()
    browser.form.set_select({"security": "low"})
    browser.submit_selected()
    browser.open(host_url)

    print("DVWA Custom Auth Complete.")


def test(host_url: str, discover_data: dict, custom_auth: bool, vectors=[], sanitized=[], sensitive=[]):
    # TODO: Implement
    print("Testing discovered urls and inputs...")
    # Init MechanicalSoup with url
    browser = mechanicalsoup.StatefulBrowser(user_agent='MechanicalSoup')
    try:
        browser.open(host_url)
    except Exception as e:
        print("Failed to connect to url '{}': {}".format(host_url, e))
        return

    # DVWA Custom Auth
    if (custom_auth):
        DVWA_custom_auth(host_url, browser)

    # Attempt to exploit vectors on discover data
    for url in discover_data:
        # Get data from data struct
        url_obj = discover_data[url]

        # Parse URL
        parsed_url = urlparse(url)

        response_data = exploit_url(parsed_url, url_obj.get("inputs"), browser, vectors, sanitized)

        # Display any non-200 responses to the user to reveal any possible exploits
        responses = 0
        for response_type in response_data:
            responses += len(response_data.get(response_type))

        # Display test response data
        if(responses > 0):
            print("Responses for tests on '{}'".format(url))
            for response_type in response_data:
                responses = response_data.get(response_type)
                if (len(responses) > 0):
                    print("Input type: '{}'".format(response_type.capitalize()))
                    for resp_reason in responses:
                        response = responses[resp_reason]
                        print("'{}' ~ '{}': [{}] - {}".format(response.url, resp_reason, response.status_code, response.reason))
                        # TODO: Implement sanitization checking
                        # if(resp_reason in response.text):
                        #     print("Sanitization failed for string '{}'".format(resp_reason))
                        resp_milli = round(response.elapsed.microseconds / 1000)
                        if(resp_milli > 75):
                            # Check for response times, as well as possiblity of DOS attack
                            print("Response took longer than expected ({} ms)".format(resp_milli))

        # Check for sensitive data to filter program output
        # TODO: Implement filtering





def exploit_url(parsed_url: ParseResult, url_data: dict, browser: mechanicalsoup.StatefulBrowser, vectors: [], sanitized: []):
    # Extract data from url obj
    query_inputs = url_data.get("query")
    form_inputs = url_data.get("forms")
    cookie_inputs = url_data.get("cookies")

    # Use all given attack vectors on each input
    q_resp = attack_query(parsed_url, browser, query_inputs, vectors)
    f_resp = attack_form(parsed_url, browser, form_inputs, sanitized)
    # c_resp = attack_cookies(parsed_url, browser, cookie_inputs, vectors)

    return {
        "q_resp": q_resp,
        "f_resp": f_resp,
        # "c_resp": c_resp
    }


# TODO: Attack methods
def attack_query(parsed_url: ParseResult, browser: mechanicalsoup.StatefulBrowser, inputs: [], vectors: []):
    responses = {}

    # If no valid inputs given, skip this method
    if inputs is None or len(inputs) == 0: return responses

    # Format url
    url = parsed_url.geturl()

    # Attack given url and its inputs, collecting responses to be returned
    for qi in inputs:
        for vector in vectors:
            # Build query str and perform request
            query_str = "?" + qi + "=" + vector
            response = browser.get(url + query_str)
            responses[vector] = response

    # Return collected responses
    return responses


# TODO: Attack methods
def attack_form(parsed_url: ParseResult, browser: mechanicalsoup.StatefulBrowser, inputs: [], sanitized: []):
    responses = {}

    # If no valid inputs given, skip this method
    if inputs is None or len(inputs) == 0: return responses

    # Format url
    url = parsed_url.geturl()

    # Open form url to attack
    browser.open(url)

    # Filter buttons from input list
    buttons = [b.get("name") for b in browser.page.find_all('input', {'name': True, 'type': "submit"})]

    # Check for lack of sanitization and store responses
    for s in sanitized:
        try:
            browser.select_form()
        except Exception as e:
            print(e)
            continue

        for fi in inputs:
            # Skip button inputs, these will be used to test other inputs
            if(fi in buttons):
                continue

            # Input sanitized chars into all inputs
            try:
                browser[fi] = s
            except ValueError as e:
                print(e)
                continue

        # Submit form and store response
        responses[s] = browser.submit_selected()

    return responses


# TODO: Attack methods
def attack_cookies(parsed_url: ParseResult, browser: mechanicalsoup.StatefulBrowser, inputs: [], vectors: []):
    responses = []

    # If no valid inputs given, skip this method
    if inputs is None or len(inputs) == 0: return responses

    for ci in inputs:
        for vector in vectors:
            a = 1

    return responses


def parse_arguments():
    """
    Parses command-line arguments from console.

    Returns:
        Parsed command-line arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["discover", "test"])
    parser.add_argument("host_url")

    # Global options
    parser.add_argument("--files-dir")
    parser.add_argument("--custom-auth", choices=["dvwa"])
    parser.add_argument("--common-words")
    parser.add_argument("--extensions")

    # Test options
    parser.add_argument("--vectors")
    parser.add_argument("--sanitized-chars")
    parser.add_argument("--sensitive")
    parser.add_argument("--slow", type=int)
    return parser.parse_args()


def load_file(base_dir: str, filepath: str):
    """
    Attempts to load the file at the specified path (split into base directory and filepath).

    Returns:
        Lines read from file into a list (newlines stripped)
    """
    # Create list to store lines
    file_lines = []

    # Skip all loading if None filepath received
    if(filepath is None):
        return file_lines

    # Build path to file
    full_path = base_dir if base_dir is not None else ""
    if (full_path != "" and not full_path.endswith("/") and not full_path.endswith("\\")):
        full_path += "/"
    full_path += filepath

    # Read in data (safe)
    try:
        if (full_path is not None and full_path != "/"):
            file_lines = ''.join(open(full_path).readlines()).splitlines()
    except Exception as e:
        print("Error accessing file '{}': {}".format(full_path, e))
        return file_lines

    # Return any loaded data
    print("Loaded file '{}' (Full Path: '{}')".format(filepath, full_path))
    return file_lines


# Main method
if(__name__ == "__main__"):
    # Parse arguments from command line
    args = parse_arguments()

    # Extract url from arguments
    url = args.host_url

    # Extract chosen command and custom auth flag from arguments
    command = args.command
    custom_auth = args.custom_auth == "dvwa"

    # Extract files directiory and validate
    files_dir = args.files_dir if args.files_dir is not None and os.path.isdir(args.files_dir) else None

    # Read in any files specified in global arguments
    cw_file = args.common_words
    cw_lines = load_file(files_dir, cw_file)

    ext_file = args.extensions
    ext_lines = load_file(files_dir, ext_file)

    # Perform user-defined action on page (discover or test)
    if(command == "discover"):
        # Init visited urls set and pass to discover method
        found_urls = {}

        discover_init(url, found_urls, custom_auth, cw_lines, ext_lines)  # Pass custom auth flag
    elif(command == "test"):
        # Read in any files specified in test-specific arguments

        vec_file = args.vectors
        vec_lines = load_file(files_dir, vec_file)

        san_file = args.sanitized_chars
        san_lines = load_file(files_dir, san_file)

        sens_file = args.sensitive
        sens_lines = load_file(files_dir, sens_file)

        # Run discover and store the data
        discover_data = {}
        discover_init(url, discover_data, custom_auth, cw_lines, ext_lines)

        # Run test command with found test data
        test(url, discover_data, custom_auth, vec_lines, san_lines, sens_lines)
