import streamlit as st
import requests
import re
import time

class ReverbListingCloner:
    def __init__(self, api_token):
        self.api_token = api_token
        self.base_url = "https://api.reverb.com/api"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/hal+json",
            "Accept": "application/hal+json",
            "Accept-Version": "3.0"
        }

    def get_slug_from_url(self, url):
        match = re.search(r'item/(\d+)', url)
        return match.group(1) if match else None

    def fetch_listing(self, listing_id):
        try:
            response = requests.get(f"{self.base_url}/listings/{listing_id}", headers=self.headers)
            return response.json() if response.status_code == 200 else None
        except:
            return None

    def build_payload(self, src, ship_id):
        try:
            # Cleans the price string and applies the 0.35 multiplier
            amount_str = str(src.get("price", {}).get("amount", "0")).replace(",", "")
            new_price = float(amount_str) * 0.35
        except:
            new_price = 0.0
        
        payload = {
            "make": src.get("make"),
            "model": src.get("model"),
            "title": src.get("title"),
            "description": src.get("description"),
            "finish": src.get("finish"),
            "year": src.get("year"),
            "handmade": src.get("handmade", False),
            "offers_enabled": False, 
            "shipping_profile_id": int(ship_id),
            "price": {
                "amount": f"{new_price:.2f}",
                "currency": "EUR" # Forced to EURO
            },
            # --- THE FIX ---
            # This marks the item as exempt from UPC/EAN requirements
            "upc_does_not_apply": True 
            # ---------------
        }

        if src.get("categories"):
            payload["categories"] = [{"uuid": src["categories"][0].get("uuid")}]
        if src.get("condition"):
            payload["condition"] = {"uuid": src["condition"].get("uuid")}

        photo_urls = []
        if src.get("photos"):
            for p in src["photos"]:
                url = p.get("_links", {}).get("large_crop", {}).get("href") or \
                      p.get("_links", {}).get("full", {}).get("href")
                if url: photo_urls.append(url)
        payload["photos"] = photo_urls
        return payload

    def create_and_publish(self, payload):
        # 1. Create the listing
        create_res = requests.post(f"{self.base_url}/listings", headers=self.headers, json=payload)
        
        if create_res.status_code not in [200, 201, 202]:
            return False, f"Creation failed: {create_res.status_code} - {create_res.text}"

        new_id = create_res.json().get("id") or create_res.json().get("listing", {}).get("id")
        
        # 2. Brief pause for Reverb to register the new ID
        time.sleep(2) 

        # 3. Publish to live
        publish_url = f"{self.base_url}/listings/{new_id}"
        publish_res = requests.put(publish_url, headers=self.headers, json={"publish": True})
        
        if 200 <= publish_res.status_code < 300:
            return True, new_id
        else:
            return False, f"Created {new_id} but failed to publish: {publish_res.text}"

# --- UI Setup ---
st.set_page_config(page_title="🎸", page_icon="🎸", layout="wide")

st.title("🎸")

with st.container():
    col_a, col_b = st.columns(2)
    with col_a:
        api_token = st.text_input("code", type="password")
        ship_id = st.text_input("ID", placeholder="e.g. 123456")
    with col_b:
        url_input = st.text_area(",...", placeholder="URL 1, URL 2...")

if st.button("🚀"):
    if not api_token or not ship_id or not url_input:
        st.warning("Please fill in all fields.")
    else:
        app = ReverbListingCloner(api_token)
        urls = [u.strip() for u in url_input.replace("\n", ",").split(",") if u.strip()]
        
        progress = st.progress(0)
        
        for idx, url in enumerate(urls):
            listing_id = app.get_slug_from_url(url)
            if listing_id:
                with st.status(f"Processing: {url}", expanded=False) as status:
                    data = app.fetch_listing(listing_id)
                    if data:
                        payload = app.build_payload(data, ship_id)
                        success, result = app.create_and_publish(payload)
                        
                        if success:
                            st.write(f"✅ Success! New Listing ID: {result} (EUR)")
                            status.update(label=f"Completed: {result}", state="complete")
                        else:
                            st.write(f"❌ Error: {result}")
                            status.update(label="Failed", state="error")
                    else:
                        st.error(f"Could not fetch source listing: {listing_id}")
            
            progress.progress((idx + 1) / len(urls))
            # Global throttle to avoid hitting API rate limits
            time.sleep(1)

        st.balloons()
        st.success("Batch Processing Finished!")
