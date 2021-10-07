from urllib.parse import quote_plus
from multiprocessing import Lock
import re
import requests
import json
import js2py
from lxml import etree

from utils import urlencode_postdata, _hidden_inputs, get_xpath, filter_children_recursive, int_or_none

class PHSession:
    def __init__(self, username=None, password=None, premium=False):
        self.username = username
        self.premium = premium
        self.base_url = f"https://www.pornhub{'premium' if premium else ''}.com"
        self.lock = Lock()
        if premium:
            self.session, resp = self.login(username, password, premium)
            if self.session is None:
                raise ValueError(resp)
        else:
            self.session = requests.Session()

    def login(self, username, password, premium):
        session = requests.Session()

        login_url = f"{self.base_url}/{'premium/' if premium else ''}login"
        login_page = session.get(login_url).text
        
        inputs = _hidden_inputs(login_page)
        inputs["username"] = username
        inputs["password"] = password

        login_url = f"{self.base_url}/front/authenticate"
        response = session.post(login_url, data=urlencode_postdata(inputs), headers={'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Referer': login_url, 'X-Requested-With': 'XMLHttpRequest'}).text
        try:
            response = json.loads(response)
        except:
            return (None, response)

        if response["success"] != "1":
            return (None, response)

        return (session, response)

    @staticmethod
    def pcvideolistitem_extract(item, needs_uploader=True):
        viewkey = item.attrib["data-video-vkey"]

        if len(filter_children_recursive(item, lambda x: "class" in x.attrib.keys() and x.attrib["class"] == "privateOverlay")) > 0:
            return (None,)

        title = filter_children_recursive(item, lambda x: "href" in x.attrib.keys() and ("view_video" in x.attrib["href"] or "javascript:void" in x.attrib["href"]))
        if len(title) != 2:
            raise ValueError(title)
        title = title[0].attrib["title"]

        thumbnail_url = filter_children_recursive(item, lambda x: "data-thumb_url" in x.attrib.keys())
        if len(thumbnail_url) != 1:
            raise ValueError(thumbnail_url)
        thumbnail_url = thumbnail_url[0].attrib["data-thumb_url"]

        duration = filter_children_recursive(item, lambda x: "class" in x.attrib.keys() and x.attrib["class"] == "duration")
        if len(duration) != 1:
            raise ValueError(duration)
        duration = duration[0].text

        views = filter_children_recursive(item, lambda x: "class" in x.attrib.keys() and x.attrib["class"] == "views")
        if len(views) != 1:
            raise ValueError(views)
        views = views[0][0].text

        likeratio = filter_children_recursive(item, lambda x: "class" in x.attrib.keys() and "rating-container" in x.attrib["class"])
        if len(likeratio) != 1:
            raise ValueError(likeratio)
        likeratio = likeratio[0][1].text

        uploader_dict = {}
        if needs_uploader:
            uploader_element = filter_children_recursive(item, lambda x: "class" in x.attrib.keys() and "usernameWrap" in x.attrib["class"])
            if len(uploader_element) != 1:
                raise ValueError(uploader_element)
            if "href" in uploader_element[0][0].attrib.keys():
                uploader_type = uploader_element[0][0].attrib["href"].split("/")[1]
                uploader_name = uploader_element[0][0].text
                uploader_internal_name = "/".join(uploader_element[0][0].attrib["href"].split("/")[2:])

                uploader_dict = {
                    "uploader": {
                        "uploader_type": uploader_type,
                        "uploader_name": uploader_name,
                        "uploader_internal_name": uploader_internal_name,
                    }
                }

        premium = len(filter_children_recursive(item, lambda x: "class" in x.attrib.keys() and "premiumIcon" in x.attrib["class"])) == 1

        return {**{
            "viewkey": viewkey,
            "title": title,
            "thumbnail": thumbnail_url,
            "duration": duration,
            "views": views,
            "like_ratio": likeratio,
            "premium": premium
        }, **uploader_dict}

    @staticmethod
    def return_video_page(videos_container, tree, needs_uploader, resolved_pages=None):
        if videos_container is None:
            raise ValueError(videos_container)

        videos = [PHSession.pcvideolistitem_extract(x, needs_uploader) for x in videos_container if "class" in x.attrib.keys() and "pcVideoListItem" in x.attrib["class"]]
        videos = [x for x in videos if x != (None,)]
        if None in videos:
            raise ValueError(videos)

        if resolved_pages is None:
            pagination_container = get_xpath(tree, "//div[@class=\"pagination3\"]")
            if pagination_container is None:
                max_page = 1
            else:
                pagenums = [y for y in [int_or_none(x[0].text) for x in pagination_container[0]] if y is not None]
                max_page = max(pagenums)
            resolved_pages = max_page

        return {
            "resolved_pages": resolved_pages,
            "results": videos
        }

    def get_from_pornhub(self, url, should_lock=True):
        with (self.lock if should_lock else Lock()):
            response = self.session.get(url).text
            if "function leastFactor" not in response:
                return response

            jscode = re.findall(r"(function leastFactor.*){ document\.cookie", response, flags=re.DOTALL)[0]
            finalline = re.findall(r"cookie.(.RNKEY.*;.);", response)[0]
            jscode += f"return {finalline};\n" + "}\ngo();"
            newcookies = [x.split("=") for x in js2py.eval_js(jscode).split(";")]
            newcookies = [x for x in newcookies if len(x) == 2]
            for cv in newcookies:
                c, v = cv
                self.session.cookies[c] = v
            print(f"set new cookies: {newcookies}")

            return self.get_from_pornhub(url, False)

    def get_video_hls_from_master(self, master_url, authtoken):
        response = self.get_from_pornhub(master_url).split("\n")
        index = [x for x in response if "index-" in x]
        if len(index) != 1:
            raise ValueError(index)
        index = index[0]

        base_url = master_url.split("/master")[0]
        index_url = base_url + "/" + index
        index_response = requests.get(index_url).text.split("\n")
        for i in range(len(index_response)):
            if "seg-" in index_response[i]:
                index_response[i] = f"https://e2d9f1653f4c.ngrok.io/redirect_request?authtoken={authtoken}&endpoint={quote_plus(base_url + '/' + index_response[i])}"

        return "\n".join(index_response)

    def get_video_info(self, viewkey):
        video_url = f"{self.base_url}/view_video.php?viewkey={viewkey}"
        video_page = self.get_from_pornhub(video_url)

        tree = etree.HTML(video_page)

        title = get_xpath(tree, "//*[@id=\"videoTitle\"]/span" if self.premium else "//*[@id=\"hd-leftColVideoPage\"]/div[1]/div[3]/h1/span")
        if title is None:
            raise ValueError(title)
        title = title.text

        thumbnail_url = get_xpath(tree, "//*[@id=\"videoElementPoster\"]")
        if thumbnail_url is None:
            raise ValueError(thumbnail_url)
        thumbnail_url = thumbnail_url.attrib["src"]

        ratinginfo_container = get_xpath(tree, "//div[@class=\"ratingInfo\"]")
        if ratinginfo_container is None:
            raise ValueError(ratinginfo_container)

        views = ratinginfo_container[0][0].text
        upload_date = ratinginfo_container[2].text

        video_container = get_xpath(tree, "//div[@class=\"video-wrapper\"]")
        if video_container is None:
            raise ValueError(video_container)

        likes = filter_children_recursive(video_container, lambda x: "class" in x.attrib.keys() and x.attrib["class"] == "votesUp")
        if len(likes) != 1:
            raise ValueError(likes)
        likes = likes[0].attrib["data-rating"]

        dislikes = filter_children_recursive(video_container, lambda x: "class" in x.attrib.keys() and x.attrib["class"] == "votesDown")
        if len(dislikes) != 1:
            raise ValueError(dislikes)
        dislikes = dislikes[0].attrib["data-rating"]

        categories_div = get_xpath(tree, "//div[@class=\"categoriesWrapper\"]")
        if categories_div is None:
            raise ValueError(categories_div)
        categories = [x.text for x in categories_div if "class" in x.attrib.keys() and x.attrib["class"] == "item"]

        uploader_div = get_xpath(tree, "//div[@class=\"userInfo\"]")
        link = filter_children_recursive(uploader_div, lambda x: "href" in x.attrib)
        if len(link) != 1:
            raise ValueError(uploader_div)
        uploader_type = link[0].attrib["href"].split("/")[1]
        uploader_name = link[0].text
        uploader_internal_name = "/".join(link[0].attrib["href"].split("/")[2:])

        related_container = get_xpath(tree, "//ul[@id=\"relatedVideosCenter\"]")
        related_videos = [PHSession.pcvideolistitem_extract(x) for x in related_container]
        related_videos = [x for x in related_videos if x != (None,)]
        if None in related_videos:
            raise ValueError(related_videos)

        pornstars_container = filter_children_recursive(tree, lambda x: "class" in x.attrib.keys() and "pornstarsWrapper" in x.attrib["class"])
        if len(pornstars_container) != 1:
            raise ValueError(pornstars_container)
        pornstars_container = pornstars_container[0]
        pornstars = filter_children_recursive(pornstars_container, lambda x: "class" in x.attrib.keys() and "pstar-list-btn" in x.attrib["class"])
        pornstars = [{"name": x.attrib["data-mxptext"], "internal_name": "/".join(x.attrib["href"].split("/")[2:]), "image": x[0].attrib["data-src"]} for x in pornstars]

        return {
            "viewkey": viewkey,
            "title": title,
            "thumbnail": thumbnail_url,
            "views": views,
            "likes": likes,
            "dislikes": dislikes,
            "upload_date": upload_date,
            "categories": categories,
            "pornstars": pornstars,
            "uploader_type": uploader_type,
            "uploader_name": uploader_name,
            "uploader_internal_name": uploader_internal_name,
            "related_videos": related_videos
        }

    def search_videos(self, query, page):
        search_url = f"{self.base_url}/video/search?search={quote_plus(query)}&page={page}"
        search_page = self.get_from_pornhub(search_url)
        open("debug.html", "wb").write(search_page.encode("ascii", "ignore"))

        tree = etree.HTML(search_page)

        search_container = get_xpath(tree, "//ul[@id=\"videoSearchResult\"]")
        return PHSession.return_video_page(search_container, tree, True)

    def get_video_streams(self, viewkey):
        video_url = f"{self.base_url}/view_video.php?viewkey={viewkey}"
        video_page = self.get_from_pornhub(video_url)

        media_matches = re.findall("media_0;(var.*var media_1=.*?;)", video_page)
        if len(media_matches) == 0:
            raise ValueError(media_matches)
        media_str = media_matches[0]

        media_exec = re.sub("\\/\\*.*?\\*\\/", "", media_str.replace("var ", ""))
        d = {}
        exec(media_exec, d)

        streams = json.loads(self.get_from_pornhub(d["media_1"]))
        return [x for x in streams if isinstance(x["defaultQuality"], bool)]
        #return streams[:-1]

    def get_model_info(self, internal_name):
        model_url = f"{self.base_url}/model/{internal_name}"
        model_page = self.get_from_pornhub(model_url)

        tree = etree.HTML(model_page)

        banner_container = get_xpath(tree, "//div[@class=\"coverImage\"]")
        if banner_container is None:
            raise ValueError(banner_container)

        name = banner_container[0].attrib["alt"]

        banner_image_url = banner_container[0].attrib["src"]

        profile_image_url = get_xpath(tree, "//img[@id=\"getAvatar\"]")
        if profile_image_url is None:
            raise ValueError(profile_image_url)
        profile_image_url = profile_image_url.attrib["src"]

        about_me_container = filter_children_recursive(tree, lambda x: "class" in x.attrib.keys() and "aboutMeSection" in x.attrib["class"])
        if len(about_me_container) != 1:
            raise ValueError(about_me_container)
        if len(about_me_container[0]) < 2:
            about_me = ""
        else:
            about_me = about_me_container[0][1].text.strip("\n\t \r")

        return {
            "name": name,
            "internal_name": internal_name,
            "about": about_me,
            "profile_picture": profile_image_url,
            "banner_picture": banner_image_url
        }

    def get_model_videos(self, internal_name, page):
        model_videos_url = f"{self.base_url}/model/{internal_name}/videos?page={page}"
        model_videos_page = self.get_from_pornhub(model_videos_url)

        tree = etree.HTML(model_videos_page)

        mrv_container = get_xpath(tree, "//ul[@id=\"mostRecentVideosSection\"]")
        return PHSession.return_video_page(mrv_container, tree, False)

    def get_pornstar_info(self, internal_name):
        pornstar_url = f"{self.base_url}/pornstar/{internal_name}"
        pornstar_page = self.get_from_pornhub(pornstar_url)

        tree = etree.HTML(pornstar_page)

        profile_container = get_xpath(tree, "//section[@class=\"topProfileHeader\"]")
        if profile_container is None:
            raise ValueError(profile_container)

        name = get_xpath(profile_container, "//div[@class=\"name\"]")
        if name is None:
            raise ValueError(name)
        name = name[0].text.strip("\n\t \r")

        bio1 = get_xpath(profile_container, "//div[@itemprop=\"description\"]")
        bio2 = get_xpath(profile_container, "//div[@class=\"bio\"]")
        if bio1 is None and bio2 is None:
            bio = ""
        if bio1 is not None:
            bio = bio1.text.strip("\n\t \r")
        elif bio2 is not None:
            bio = bio2[1].text.strip("\n\t \r")

        img1 = get_xpath(profile_container, "//img[@id=\"getAvatar\"]")
        img2 = get_xpath(profile_container, "//div[@class=\"thumbImage\"]")
        if img1 is None and img2 is None:
            raise ValueError((img1, img2))
        if img1 is not None:
            img = img1.attrib["src"]
        else:
            img = img2[0].attrib["src"]

        return {
            "name": name,
            "internal_name": internal_name,
            "bio": bio,
            "picture": img
        }

    def get_pornstar_videos(self, internal_name, page):
        pornstar_videos_url = f"{self.base_url}/pornstar/{internal_name}?page={page}"
        pornstar_videos_page = self.get_from_pornhub(pornstar_videos_url)

        tree = etree.HTML(pornstar_videos_page)

        videos_container = get_xpath(tree, "//ul[@id=\"pornstarsVideoSection\"]")
        if videos_container is None:
            pornstar_videos_url = f"{self.base_url}/pornstar/{internal_name}/videos?page={page}"
            pornstar_videos_page = self.get_from_pornhub(pornstar_videos_url)

            tree = etree.HTML(pornstar_videos_page)

            videos_container = get_xpath(tree, "//ul[@id=\"mostRecentVideosSection\"]")
            if videos_container is None:
                raise ValueError(videos_container)

        return PHSession.return_video_page(videos_container, tree, True)

    def search_pornstars(self, query, page):
        search_url = f"{self.base_url}/pornstars/search?search={quote_plus(query)}&page={page}"
        search_page = self.get_from_pornhub(search_url)

        tree = etree.HTML(search_page)

        ps_container = get_xpath(tree, "//ul[@id=\"pornstarsSearchResult\"]")
        if ps_container is None:
            raise ValueError(ps_container)
        wraps = filter_children_recursive(ps_container, lambda x: "class" in x.attrib.keys() and x.attrib["class"] == "wrap")
        names = [x[2][0].text for x in wraps]
        internal_names = ["/".join(x[2][0].attrib["href"].split("/")[2:]) for x in wraps]
        pictures = []
        for i in wraps:
            dtu = filter_children_recursive(i, lambda x: "data-thumb_url" in x.attrib.keys())
            if len(dtu) != 1:
                raise ValueError(dtu)
            pictures.append(dtu[0].attrib["data-thumb_url"])
        if len(names) != len(internal_names) and len(internal_names) != len(pictures):
            raise ValueError((names, internal_names, pictures))
        pornstars = [{"name": x[0], "internal_name": x[1], "picture": x[2]} for x in zip(names, internal_names, pictures)]

        pagination_container = get_xpath(tree, "//div[@class=\"pagination3\"]")
        if pagination_container is None:
            max_page = 1
        else:
            pagenums = [y for y in [int_or_none(x[0].text) for x in pagination_container[0]] if y is not None]
            max_page = max(pagenums)

        return {
            "resolved_pages": max_page,
            "results": pornstars
        }

    def get_channel_info(self, internal_name):
        channel_url = f"{self.base_url}/channels/{internal_name}"
        channel_page = self.get_from_pornhub(channel_url)

        tree = etree.HTML(channel_page)

        profile_section = get_xpath(tree, "//section[@id=\"channelsProfile\"]")
        if profile_section is None:
            raise ValueError(profile_section)
        
        #_name = filter_children_recursive(profile_section[0], lambda x: "class" in x.attrib.keys() and "title" in x.attrib["class"].split(" "))
        _name = get_xpath(tree, "//div[@class=\"title floatLeft\"]")
        if _name is None:
            raise ValueError(_name)
        name = _name[0].text
        if name is None:
            name = _name[1].text
        _ = """
        if len(_name) != 1:
            raise ValueError(name)
        name = _name[0][0].text
        if name is None:
            name = _name[1].text"""

        desc = get_xpath(tree, "//div[@class=\"cdescriptions\"]")
        if desc is None:
            raise ValueError(desc)
        desc = desc[0].text.strip("\n\t \r")

        image = get_xpath(tree, "//img[@id=\"getAvatar\"]")
        if image is None:
            raise ValueError(image)
        image = image.attrib["src"]

        banner_image = get_xpath(tree, "//img[@id=\"coverPictureDefault\"]")
        if banner_image is None:
            raise ValueError(banner_image)
        banner_image = banner_image.attrib["src"]

        return {
            "name": name,
            "internal_name": internal_name,
            "description": desc,
            "picture": image,
            "banner_picture": banner_image
        }

    def get_channel_videos(self, internal_name, sort, page):
        sort = {"recent": "da", "rated": "ra", "viewed": "vi"}[sort]
        channel_videos_url = f"{self.base_url}/channels/{internal_name}/videos?o={sort}&page={page}"
        channel_videos_page = self.get_from_pornhub(channel_videos_url)

        tree = etree.HTML(channel_videos_page)

        videos_container = get_xpath(tree, "//ul[@id=\"showAllChanelVideos\"]")
        return PHSession.return_video_page(videos_container, tree, False)

    def frontpage_region(self, sort, page, timespan=None):
        sort = {"hottest": "ht", "viewed": "mv", "rated": "tr"}[sort]
        fp_videos_url = f"{self.base_url}/video?o={sort}&page={page}"
        if timespan is not None:
            timespan = {"week": "w", "month": "m", "all": "a"}[timespan]
            fp_videos_url += f"&t={timespan}"
        fp_videos_page = self.get_from_pornhub(fp_videos_url)

        tree = etree.HTML(fp_videos_page)

        videos_container = get_xpath(tree, "//ul[@id=\"videoCategory\"]")
        return PHSession.return_video_page(videos_container, tree, True)

    def recommended(self, page):
        rec_videos_url = f"{self.base_url}/recommended?page={page}"
        rec_videos_page = self.get_from_pornhub(rec_videos_url)

        tree = etree.HTML(rec_videos_page)

        videos_container = get_xpath(tree, "//ul[@id=\"recommendedListings\"]")
        return PHSession.return_video_page(videos_container, tree, True)

    @staticmethod
    def videos_page_is_empty(page):
        return "There are no videos..." in page

    @staticmethod
    def videos_page_exists(page):
        return "Error Page Not Found" not in page

    def history(self, page, resolved_pages=None):
        history_videos_url = f"{self.base_url}/users/{self.username}/videos/recent?page={page}"
        history_videos_page = self.get_from_pornhub(history_videos_url)

        if resolved_pages is None:
            lb = 1
            ub = 50

            if self.videos_page_is_empty(self.get_from_pornhub(f"{self.base_url}/users/{self.username}/videos/recent")):
                return {
                    "resolved_pages": 0,
                    "results": []
                }

            while self.videos_page_exists(self.get_from_pornhub(f"{self.base_url}/users/{self.username}/videos/recent?page={ub}")):
                ub += 50

            while not (lb == (ub - 1)):
                guess = (lb + ub) // 2
                if self.videos_page_exists(self.get_from_pornhub(f"{self.base_url}/users/{self.username}/videos/recent?page={guess}")):
                    lb = guess
                else:
                    ub = guess

            resolved_pages = lb

        tree = etree.HTML(history_videos_page)

        videos_container = get_xpath(tree, "//ul[@id=\"moreData\"]")
        return PHSession.return_video_page(videos_container, tree, True, resolved_pages)
