import uuid
import json
import requests

from flask import Flask, request, Response

from phapi import PHSession

app = Flask(__name__)

@app.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = '*'
    return response

sessions = {}

@app.route("/redirect_request")
def redirect_request():
    uid = request.args.get("authtoken")
    endpoint = request.args.get("endpoint")
    session = sessions[uid]
    rresponse = session.session.get(endpoint)
    response = Response(rresponse.content)
    for h in rresponse.headers.keys():
        response.headers[h] = rresponse.headers[h]
    return response

@app.route("/authenticate")
def authenticate():
    premium = request.args.get("premium") == "true"
    username = request.args.get("username")
    password = request.args.get("password")
    session = PHSession(username, password, premium)
    uid = str(uuid.uuid4())
    sessions[uid] = session
    return uid

@app.route("/video/info")
def video_info():
    uid = request.args.get("authtoken")
    viewkey = request.args.get("viewkey")
    session = sessions[uid]
    info = session.get_video_info(viewkey)
    return json.dumps(info)

@app.route("/video/search")
def video_search():
    uid = request.args.get("authtoken")
    query = request.args.get("query")
    page = request.args.get("page")
    session = sessions[uid]
    result = session.search_videos(query, int(page))
    return json.dumps(result)

@app.route("/video/stream/masters")
def video_stream():
    uid = request.args.get("authtoken")
    viewkey = request.args.get("viewkey")
    session = sessions[uid]
    streams = session.get_video_streams(viewkey)
    return json.dumps(streams)

@app.route("/video/stream/m3u8")
def video_m3u8():
    uid = request.args.get("authtoken")
    session = sessions[uid]
    master_url = request.args.get("master_url")
    resp = session.get_video_hls_from_master(master_url, uid)
    response = Response(resp)
    response.headers["content-type"] = "application/vnd.apple.mpegurl"
    return response

@app.route("/model/info")
def model_info():
    uid = request.args.get("authtoken")
    name = request.args.get("name")
    session = sessions[uid]
    info = session.get_model_info(name)
    return json.dumps(info)

@app.route("/model/videos")
def model_videos():
    uid = request.args.get("authtoken")
    name = request.args.get("name")
    page = request.args.get("page")
    session = sessions[uid]
    result = session.get_model_videos(name, int(page))
    return json.dumps(result)

@app.route("/pornstar/info")
def pornstar_info():
    uid = request.args.get("authtoken")
    name = request.args.get("name")
    session = sessions[uid]
    info = session.get_pornstar_info(name)
    return json.dumps(info)

@app.route("/pornstar/videos")
def pornstar_videos():
    uid = request.args.get("authtoken")
    name = request.args.get("name")
    page = request.args.get("page")
    session = sessions[uid]
    result = session.get_pornstar_videos(name, int(page))
    return json.dumps(result)

@app.route("/pornstar/search")
def pornstar_search():
    uid = request.args.get("authtoken")
    query = request.args.get("query")
    page = request.args.get("page")
    session = sessions[uid]
    result = session.search_pornstars(query, int(page))
    return json.dumps(result)

@app.route("/channel/info")
def channel_info():
    uid = request.args.get("authtoken")
    name = request.args.get("name")
    session = sessions[uid]
    info = session.get_channel_info(name)
    return json.dumps(info)

@app.route("/channel/videos")
def channel_videos():
    uid = request.args.get("authtoken")
    name = request.args.get("name")
    sort = request.args.get("sort")
    page = request.args.get("page")
    session = sessions[uid]
    result = session.get_channel_videos(name, sort, int(page))
    return json.dumps(result)

@app.route("/frontpage/region")
def frontpage_region():
    uid = request.args.get("authtoken")
    sort = request.args.get("sort")
    page = request.args.get("page")
    timespan = request.args.get("timespan")
    session = sessions[uid]
    result = session.frontpage_region(sort, page, timespan)
    return json.dumps(result)

@app.route("/frontpage/recommended")
def frontpage_recommended():
    uid = request.args.get("authtoken")
    page = request.args.get("page")
    session = sessions[uid]
    result = session.recommended(sort, page)
    return json.dumps(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0")
