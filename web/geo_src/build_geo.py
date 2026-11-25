"""build_geo.py  สร้าง site/data/geo.json จากไฟล์เข้ารหัสใน geo_src/

แหล่งข้อมูล
- provinces.txt : ขอบเขตจังหวัด geoBoundaries gbOpen THA ADM1 (OSM, ODbL) ย่อด้วย Douglas-Peucker 0.02°
- amphoe.txt    : ขอบเขตอำเภอ geoBoundaries gbOpen THA ADM2 (OSM, ODbL) เฉพาะพื้นที่ศึกษา ย่อ 0.004°
- rivers.txt    : แนวแม่น้ำจาก OpenStreetMap (Nominatim, ODbL) กก r9068461, รวก r9068459, ฝาง r9068460,
                  โขง r215354 (ตัดเฉพาะพื้นที่ศึกษา), สาย (ways ชื่อ Mae Sai River) ย่อ 0.0006°
รูปแบบเข้ารหัส: name|x0,y0,dx,dy,...  (จำนวนเต็ม = องศา × scale, ต่อ ring คั่นด้วย ;)
รัน: python site/geo_src/build_geo.py
"""
from pathlib import Path
import json
import math

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "geo.json"

PROV_TH = {
    "Amnat Charoen": "อำนาจเจริญ", "Ang Thong": "อ่างทอง", "Bangkok": "กรุงเทพมหานคร", "Bueng Kan": "บึงกาฬ",
    "Buri Ram": "บุรีรัมย์", "Chachoengsao": "ฉะเชิงเทรา", "Chai Nat": "ชัยนาท", "Chaiyaphum": "ชัยภูมิ",
    "Chanthaburi": "จันทบุรี", "Chiang Mai": "เชียงใหม่", "Chiang Rai": "เชียงราย", "Chon Buri": "ชลบุรี",
    "Chumphon": "ชุมพร", "Kalasin": "กาฬสินธุ์", "Kamphaeng Phet": "กำแพงเพชร", "Kanchanaburi": "กาญจนบุรี",
    "Khon Kaen": "ขอนแก่น", "Krabi": "กระบี่", "Lampang": "ลำปาง", "Lamphun": "ลำพูน", "Loei": "เลย",
    "Lopburi": "ลพบุรี", "Mae Hong Son": "แม่ฮ่องสอน", "Maha Sarakham": "มหาสารคาม", "Mukdahan": "มุกดาหาร",
    "Nakhon Nayok": "นครนายก", "Nakhon Pathom": "นครปฐม", "Nakhon Phanom": "นครพนม",
    "Nakhon Ratchasima": "นครราชสีมา", "Nakhon Sawan": "นครสวรรค์", "Nakhon Si Thammarat": "นครศรีธรรมราช",
    "Nan": "น่าน", "Narathiwat": "นราธิวาส", "Nong Bua Lam Phu": "หนองบัวลำภู", "Nong Khai": "หนองคาย",
    "Nonthaburi": "นนทบุรี", "Pathum Thani": "ปทุมธานี", "Pattani": "ปัตตานี", "Phangnga": "พังงา",
    "Phatthalung": "พัทลุง", "Phayao": "พะเยา", "Phetchabun": "เพชรบูรณ์", "Phetchaburi": "เพชรบุรี",
    "Phichit": "พิจิตร", "Phitsanulok": "พิษณุโลก", "Phra Nakhon Si Ayutthaya": "พระนครศรีอยุธยา",
    "Phrae": "แพร่", "Phuket": "ภูเก็ต", "Prachin Buri": "ปราจีนบุรี", "Prachuap Khiri Khan": "ประจวบคีรีขันธ์",
    "Ranong": "ระนอง", "Ratchaburi": "ราชบุรี", "Rayong": "ระยอง", "Roi Et": "ร้อยเอ็ด", "Sa Kaeo": "สระแก้ว",
    "Sakon Nakhon": "สกลนคร", "Samut Prakan": "สมุทรปราการ", "Samut Sakhon": "สมุทรสาคร",
    "Samut Songkhram": "สมุทรสงคราม", "Saraburi": "สระบุรี", "Satun": "สตูล", "Si Sa Ket": "ศรีสะเกษ",
    "Sing Buri": "สิงห์บุรี", "Songkhla": "สงขลา", "Sukhothai": "สุโขทัย", "Suphan Buri": "สุพรรณบุรี",
    "Surat Thani": "สุราษฎร์ธานี", "Surin": "สุรินทร์", "Tak": "ตาก", "Trang": "ตรัง", "Trat": "ตราด",
    "Ubon Ratchathani": "อุบลราชธานี", "Udon Thani": "อุดรธานี", "Uthai Thani": "อุทัยธานี",
    "Uttaradit": "อุตรดิตถ์", "Yala": "ยะลา", "Yasothon": "ยโสธร",
}
AMPHOE_TH = {
    "Chai Prakan": ("ไชยปราการ", "เชียงใหม่"), "Chiang Dao": ("เชียงดาว", "เชียงใหม่"), "Fang": ("ฝาง", "เชียงใหม่"),
    "Mae Ai": ("แม่อาย", "เชียงใหม่"), "Phrao": ("พร้าว", "เชียงใหม่"),
    "Chiang Kham": ("เชียงคำ", "พะเยา"), "Chun": ("จุน", "พะเยา"), "Phu Sang": ("ภูซาง", "พะเยา"),
    "Pa Daet": ("ป่าแดด", "เชียงราย"), "Phan": ("พาน", "เชียงราย"), "Chiang Khong": ("เชียงของ", "เชียงราย"),
    "Chiang Saen": ("เชียงแสน", "เชียงราย"), "Doi Luang": ("ดอยหลวง", "เชียงราย"), "Khun Tan": ("ขุนตาล", "เชียงราย"),
    "Mae Chan": ("แม่จัน", "เชียงราย"), "Mae Fa Luang": ("แม่ฟ้าหลวง", "เชียงราย"), "Mae Lao": ("แม่ลาว", "เชียงราย"),
    "Mae Sai": ("แม่สาย", "เชียงราย"), "Mae Suai": ("แม่สรวย", "เชียงราย"),
    "Mueang Chiang Rai": ("เมืองเชียงราย", "เชียงราย"), "Phaya Mengrai": ("พญาเม็งราย", "เชียงราย"),
    "Song Khwae": ("สองแคว", "น่าน"), "Thoeng": ("เทิง", "เชียงราย"), "Wiang Chai": ("เวียงชัย", "เชียงราย"),
    "Wiang Chiang Rung": ("เวียงเชียงรุ้ง", "เชียงราย"), "Wiang Kaen": ("เวียงแก่น", "เชียงราย"),
}
RIVER_TH = {"kok": "แม่น้ำกก", "fang": "แม่น้ำฝาง", "sai": "แม่น้ำสาย", "ruak": "แม่น้ำรวก", "mekong": "แม่น้ำโขง",
            "mekong_lower": "แม่น้ำโขง (ลาว–กัมพูชา–เวียดนาม)", "salween": "แม่น้ำสาละวิน"}
# แม่น้ำไหลลงสายไหน (ใช้ให้อนุภาคไหลต่อ)
DOWNSTREAM = {"fang": "kok", "kok": "mekong", "sai": "ruak", "ruak": "mekong", "mekong": "mekong_lower",
              "mekong_lower": None, "salween": None}
import re
STATION_RIVER = [(r"^KK\d", "kok"), (r"^FA\d", "fang"), (r"^SA\d", "sai"), (r"^RU\d", "ruak"), (r"^NK\d", "mekong"),
                 (r"^E9-NK\d", "mekong"), (r"^SAL\d", "salween")]


def river_of(sid):
    for pat, rv in STATION_RIVER:
        if re.match(pat, sid):
            return rv
    return None


def decode(path, scale):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, body = line.split("|", 1)
        rings = []
        for ring in body.split(";"):
            v = [int(t) for t in ring.split(",")]
            x = y = 0
            pts = []
            for i in range(0, len(v), 2):
                x += v[i]; y += v[i + 1]
                pts.append([round(x / scale, 5), round(y / scale, 5)])
            rings.append(pts)
        out.append((name, rings))
    return out


def smooth(pts, k=2):
    out = []
    for i in range(len(pts)):
        a, b = max(0, i - k), min(len(pts), i + k + 1)
        out.append([round(sum(p[0] for p in pts[a:b]) / (b - a), 5), round(sum(p[1] for p in pts[a:b]) / (b - a), 5)])
    return out


def nearest(pts, p):
    return min(range(len(pts)), key=lambda i: (pts[i][0] - p[0]) ** 2 + (pts[i][1] - p[1]) ** 2)


def main():
    stations = json.loads((HERE.parent / "data" / "observations.json").read_text(encoding="utf-8"))
    st = {s["station_id"]: [s["lon"], s["lat"]] for s in stations if s.get("lat")}

    prov = [{"name": n.replace(" Province", ""), "name_th": PROV_TH.get(n.replace(" Province", ""), n), "rings": r}
            for n, r in decode(HERE / "provinces.txt", 100)]
    amph = [{"name": n, "name_th": AMPHOE_TH.get(n, (n, ""))[0], "province_th": AMPHOE_TH.get(n, ("", ""))[1], "rings": r}
            for n, r in decode(HERE / "amphoe.txt", 1000)]
    rivers = {n: r[0] for n, r in decode(HERE / "rivers.txt", 10000)}

    # แม่น้ำสาย: ข้อมูล OSM เป็นท่อนสั้น จึงเรียงตามลองจิจูด ทำให้เรียบ แล้วต่อผ่าน SA03 ไปบรรจบแม่น้ำรวก
    sai = smooth(rivers["sai"], 2)
    if "SA03" in st:
        sai.append(st["SA03"])
    j = nearest(rivers["ruak"], st.get("RU01", sai[-1]))
    join_pt = rivers["ruak"][max(0, j - 3)]
    sai.append(join_pt)
    rivers["sai"] = sai

    # แม่น้ำโขงช่วงยาว (OSM r215354, ลดจุดด้วย Douglas-Peucker 0.006°) ต่อท้ายช่วงละเอียดในลุ่มน้ำกก
    ex = {n: r[0] for n, r in decode(HERE / "rivers_extra.txt", 1000)}
    up = rivers["mekong"]
    k = nearest(ex["A"], up[-1])
    rivers["mekong"] = up + ex["A"][k + 1:]
    rivers["mekong_lower"] = ex["B"]
    rivers["salween"] = ex["C"]

    out_rivers = []
    for key, pts in rivers.items():
        down = DOWNSTREAM[key]
        join_idx = nearest(rivers[down], pts[-1]) if down else None
        anchors = {sid: nearest(pts, p) for sid, p in st.items() if river_of(sid) == key}
        out_rivers.append({"id": key, "name_th": RIVER_TH[key], "pts": pts, "downstream": down,
                           "join_index": join_idx, "anchors": anchors})

    # แม่น้ำสายหลักอื่นของไทย (OSM, ลดจุด 0.012°) ใช้เป็นภาพพื้นหลังเท่านั้น ไม่มีข้อมูลสารหนู
    THAI = {"ping": ("แม่น้ำปิง", "เจ้าพระยา → อ่าวไทย"), "wang": ("แม่น้ำวัง", "ปิง → เจ้าพระยา"), "yom": ("แม่น้ำยม", "น่าน → เจ้าพระยา"),
            "nan": ("แม่น้ำน่าน", "เจ้าพระยา → อ่าวไทย"), "chaophraya": ("แม่น้ำเจ้าพระยา", "อ่าวไทย"), "pasak": ("แม่น้ำป่าสัก", "เจ้าพระยา → อ่าวไทย"),
            "thachin": ("แม่น้ำท่าจีน", "อ่าวไทย"), "maeklong": ("แม่น้ำแม่กลอง", "อ่าวไทย"), "khwaenoi": ("แม่น้ำแควน้อย", "แม่กลอง → อ่าวไทย"),
            "bangpakong": ("แม่น้ำบางปะกง", "อ่าวไทย"), "mun": ("แม่น้ำมูล", "โขง ที่ อ.โขงเจียม"), "chi": ("แม่น้ำชี", "มูล → โขง"),
            "songkhram": ("แม่น้ำสงคราม", "โขง ที่ อ.ท่าอุเทน"), "loei": ("แม่น้ำเลย", "โขง ที่ อ.เชียงคาน"), "ing": ("แม่น้ำอิง", "โขง ที่ อ.เชียงของ")}
    thai = [{"id": n, "name_th": THAI[n][0], "to": THAI[n][1], "pts": r[0]} for n, r in decode(HERE / "rivers_thai.txt", 1000)]

    geo = {"source": "geoBoundaries gbOpen THA (ODbL), OpenStreetMap contributors (ODbL): Mekong r215354, Salween r215411",
           "provinces": prov, "amphoe": amph, "rivers": out_rivers, "thai_rivers": thai}
    OUT.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("geo.json", OUT.stat().st_size, "bytes;", len(prov), "provinces,", len(amph), "amphoe,",
          {r["id"]: (len(r["pts"]), r["anchors"]) for r in out_rivers})


if __name__ == "__main__":
    main()
