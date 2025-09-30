import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import os
import json
from datetime import datetime
import pytz
import git
from dotenv import load_dotenv
import time
import signal
import sys
import random # <-- THÊM MỚI

# --- THÊM MỚI: Danh sách các User-Agent để xoay vòng ---
USER_AGENT_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.31',
]

# --- PHẦN XỬ LÝ CTRL+C VÀ CÁC HÀM TIỆN ÍCH KHÁC (Giữ nguyên) ---
# ... (Toàn bộ các hàm và cấu hình từ các bước trước giữ nguyên) ...
shutdown_requested = False
def signal_handler(sig, frame):
    global shutdown_requested
    if not shutdown_requested:
        print("\n\n[!] Ctrl+C detected! Finishing current tasks gracefully before exiting...")
        print("[!] Press Ctrl+C again to force quit (not recommended).")
        shutdown_requested = True
    else:
        exit(1)
signal.signal(signal.SIGINT, signal_handler)
load_dotenv()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_FOLDER = os.path.join(os.path.dirname(SCRIPT_DIR), "domain")
LOG_FILE = os.path.join(os.path.dirname(SCRIPT_DIR), "productcrawler.log")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
MAX_URLS = 1000
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy tệp cấu hình tại '{CONFIG_FILE}'!")
        return None
    except json.JSONDecodeError:
        print(f"Lỗi: Tệp {CONFIG_FILE} không phải là file JSON hợp lệ.")
        return None
def save_urls(domain, new_urls):
    """Lưu các URL vào tệp trong thư mục /domain/ ở thư mục gốc."""
    os.makedirs(DOMAIN_FOLDER, exist_ok=True)
    
    filename = os.path.join(DOMAIN_FOLDER, f"{domain}.txt")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            existing_urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        existing_urls = []
        
    unique_new_urls = [u for u in new_urls if u not in existing_urls]
    
    if not unique_new_urls:
        print(f"[{domain}] No new URLs found. Total remains: {len(existing_urls)}")
        return 0, len(existing_urls)

    all_urls = unique_new_urls + existing_urls
    all_urls = all_urls[:MAX_URLS]
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(all_urls))
        
    print(f"[{domain}] Added {len(unique_new_urls)} new URLs. Total: {len(all_urls)}")
    return len(unique_new_urls), len(all_urls)

def send_telegram_message(message):
    """Gửi tin nhắn thông báo kết quả qua Telegram."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not token or not chat_id:
        print("\n[!] Cảnh báo: TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID chưa được thiết lập.")
        return

    max_len = 4096
    if len(message) > max_len:
        message = message[:max_len - 15] + "\n\n... (cắt bớt)"

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    
    try:
        response = requests.post(api_url, data=payload, timeout=10)
        if response.status_code == 200:
            print("\n--- Telegram notification sent successfully! ---")
        else:
            print(f"\n[!] Lỗi khi gửi thông báo Telegram: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"\n[!] Lỗi mạng khi gửi thông báo Telegram: {e}")

def push_to_github(commit_message):
    """Tự động add, commit --amend, và force push tất cả thay đổi lên GitHub."""
    pat = os.environ.get('CHANKTB_PAT')
    if not pat:
        print("\n[!] Cảnh báo: Biến môi trường CHANKTB_PAT chưa được thiết lập.")
        return

    print("\n--- Starting GitHub push process (using amend & force push)... ---")
    try:
        repo = git.Repo(search_parent_directories=True)

        committer_email = "4204179+chanktb@users.noreply.github.com"
        committer_name = "chanktb"

        with repo.config_writer() as git_config:
            git_config.set_value("user", "email", committer_email)
            git_config.set_value("user", "name", committer_name)
        print(f"    -> Set committer identity to: {committer_name} <{committer_email}>")

        if not repo.is_dirty(untracked_files=True):
            print("    -> No new changes to commit.")
            return

        repo.git.add(all=True)
        print("    -> Staged all changes.")
        
        repo.git.commit('--amend', m=commit_message)
        print(f"    -> Amended last commit with message: '{commit_message}'")
        
        origin = repo.remote(name='origin')
        original_url = origin.url
        
        if f"https://{pat}@" not in original_url:
            auth_repo_url = original_url.replace("https://", f"https://{pat}@")
        else:
            auth_repo_url = original_url

        with origin.config_writer as writer:
            writer.set("url", auth_repo_url)
        
        print("    -> Force pushing to remote...")
        
        # --- THAY ĐỔI DUY NHẤT Ở ĐÂY ---
        # Chỉ định rõ ràng nhánh local và nhánh remote để push
        active_branch = repo.active_branch.name
        origin.push(refspec=f'{active_branch}:{active_branch}', force=True)
        # --- KẾT THÚC THAY ĐỔI ---
        
        with origin.config_writer as writer:
            writer.set("url", original_url)

        print("--- Successfully pushed to GitHub! ---")

    except git.exc.InvalidGitRepositoryError as e:
        print(f"[!] Lỗi: Không tìm thấy kho chứa Git hợp lệ. Chi tiết: {e}")
    except git.exc.GitCommandError as e:
        print(f"[!] Lỗi khi thực thi lệnh Git: {e}")
    except Exception as e:
        print(f"[!] Một lỗi không xác định đã xảy ra khi đẩy lên GitHub: {e}")

# --- SỬA ĐỔI HÀM fetch_urls ---
def fetch_urls(url_data, use_proxy=False, proxy_template=None):
    """Tải và phân tích các URL, sử dụng User-Agent ngẫu nhiên."""
    # Chọn một User-Agent ngẫu nhiên từ danh sách cho mỗi yêu cầu
    random_user_agent = random.choice(USER_AGENT_LIST)
    headers = {"User-Agent": random_user_agent}
    print(f"    -> Using User-Agent: {random_user_agent[:50]}...") # In ra để kiểm tra
    
    target_url = url_data['url']
    if use_proxy and proxy_template:
        target_url = proxy_template.format(url=target_url)
        print(f"    -> Using proxy: {target_url[:80]}...")
    else:
        print(f"    -> Using direct connection...")
    
    try:
        r = requests.get(target_url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except requests.exceptions.RequestException as e:
        print(f"    -> Lỗi khi truy cập {url_data['url']}: {e}")
        return []

    links = []
    for a in soup.select(url_data['selector']):
        href = a.get("href")
        if href and href.startswith('http') and href not in links:
            links.append(href)
    return links


# --- HÀM CHÍNH ---
if __name__ == "__main__":
    start_time = time.time()

    config = load_config()
    if not config:
        exit(1)

    # ... (Phần code crawl từ đầu đến hết vòng lặp for giữ nguyên) ...
    # ...
    use_proxy = config.get("use_proxy", False)
    if len(sys.argv) > 1:
        mode_arg = sys.argv[1].lower()
        if mode_arg == "proxy": use_proxy = True
        elif mode_arg == "direct": use_proxy = False
    
    urls_summary = {}
    total_new_urls = 0
    vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
    timestamp = datetime.now(vn_timezone)
    
    print(f"--- Starting crawl at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    proxy_template = config.get("proxy_url_template")
    sites_to_crawl = config.get("sites", [])
    crawl_start_time = time.time()

    for url_data in sites_to_crawl:
        if shutdown_requested: break
        try:
            domain = urlparse(url_data['url']).netloc
            print(f"\nProcessing domain: {domain} ({url_data['url']})") # Thêm URL cụ thể để dễ theo dõi
            urls = fetch_urls(url_data, use_proxy, proxy_template)
            new_urls, total_urls = save_urls(domain, urls)
        
            # --- ĐOẠN SỬA LỖI ---
            # Nếu domain chưa có trong summary, hãy khởi tạo nó
            if domain not in urls_summary:
                urls_summary[domain] = {'new_count': 0, 'total_count': 0}
        
            # Cộng dồn số URL mới và cập nhật tổng số cuối cùng
            urls_summary[domain]['new_count'] += new_urls
            urls_summary[domain]['total_count'] = total_urls # Luôn gán tổng số mới nhất
            # --- KẾT THÚC SỬA LỖI ---
                    
            total_new_urls += new_urls
        except Exception as e:
            print(f"!!! ERROR processing {url_data.get('url', 'N/A')}: {e}")
    # ... (Hết vòng lặp for) ...

    crawl_end_time = time.time()
    crawl_duration = crawl_end_time - crawl_start_time
    print("\n--- Crawling finished. Creating summary... ---")

    # Tạo nội dung log và commit (luôn luôn thực hiện)
    log_header = f"--- Summary of Last Product Crawl ---\nGenerated at: {timestamp.strftime('%Y-%m-%d %H:%M:%S %z')}\n"
    log_lines = []
    for domain, counts in sorted(urls_summary.items()):
        line = f"{domain}: {counts['new_count']} New Products: {counts['total_count']}"
        log_lines.append(line)
    
    finished_line = f"\nCrawl duration: {crawl_duration:.2f} seconds."
    full_log_content = log_header + "\n" + "\n".join(log_lines) + finished_line
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(full_log_content)
    print(f"--- Summary saved to {LOG_FILE} ---")

    # Tạo commit message
    if total_new_urls > 0:
        commit_subject = f"Crawl results: {total_new_urls} new URLs found ({timestamp.strftime('%Y-%m-%d %H:%M')})"
        commit_body_lines = []
        for domain, counts in sorted(urls_summary.items()):
            if counts['new_count'] > 0:
                commit_body_lines.append(f"- {domain}: +{counts['new_count']} new URLs")
        commit_msg = commit_subject + "\n\n" + "\n".join(commit_body_lines)
    else:
        commit_msg = f"Update crawl log: No new products found ({timestamp.strftime('%Y-%m-%d %H:%M')})"

    # --- ĐƯA LOGIC GỬI TIN NHẮN CÓ ĐIỀU KIỆN TRỞ LẠI ---
    if total_new_urls > 0:
        print("\n--- New URLs found, preparing Telegram notification... ---")
        telegram_lines = [line for line in log_lines if " 0 New Products:" not in line]
        telegram_message = log_header + "\n" + "\n".join(telegram_lines) + finished_line
        send_telegram_message(telegram_message)
    else:
        print("\n--- No new URLs found, skipping Telegram notification. ---")
    # --- KẾT THÚC PHẦN KHÔI PHỤC ---

    # Kiểm tra môi trường trước khi push
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        print("\n--- Running in GitHub Actions. Skipping local push step. ---")
    else:
        push_to_github(commit_msg)

    # Chỉ in tổng thời gian ra màn hình để theo dõi
    end_time = time.time()
    duration = end_time - start_time
    print(f"\nTotal execution time: {duration:.2f} seconds.")
    
    if shutdown_requested:
        print("\n--- Graceful shutdown complete. ---")
    
    print("\n--- Process finished. ---")
