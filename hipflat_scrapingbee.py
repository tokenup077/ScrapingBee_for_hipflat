"""
Hipflat のパタヤのアパート賃貸情報を ScrapingBee を使用してスクレイピングし、
Google Sheets に出力するシステム
"""

import os
import time
import re
import random
from datetime import datetime
import pandas as pd
import logging
import json
from bs4 import BeautifulSoup
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

class HipflatScraper:
    def __init__(self, scrapingbee_api_key=None, spreadsheet_id=None):
        """
        ScrapingBeeを使用してHipflatをスクレイピングするクラスの初期化
        
        Args:
            scrapingbee_api_key: ScrapingBee APIキー (Noneの場合は環境変数から取得)
            spreadsheet_id: データを出力するGoogle SheetsのID (Noneの場合は環境変数から取得)
        """
        # 環境変数からの読み込みをサポート
        self.api_key = scrapingbee_api_key or os.environ.get('SCRAPINGBEE_API_KEY')
        self.spreadsheet_id = spreadsheet_id or os.environ.get('SPREADSHEET_ID')
        self.base_url = "https://www.hipflat.co.th/ja/apartment-for-rent/pattaya"
        self.google_sheets_client = None
        
        # Google Sheetsに接続する場合
        if self.spreadsheet_id:
            self.initialize_google_sheets()
    
    def initialize_google_sheets(self):
        """Google Sheetsへの接続を初期化"""
        try:
            # APIスコープを設定
            scope = ['https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive']
            
            # 認証情報の取得方法: ファイルかJSON文字列か
            creds = None
            
            # 環境変数からJSON文字列を取得する場合
            if 'GOOGLE_CREDENTIALS' in os.environ:
                import json
                from io import StringIO
                # 環境変数から認証情報を取得
                json_str = os.environ.get('GOOGLE_CREDENTIALS')
                # JSON文字列をパースしてクレデンシャルを作成
                json_data = json.loads(json_str)
                creds = ServiceAccountCredentials.from_json_keyfile_dict(json_data, scope)
                logger.info("環境変数から認証情報を取得しました")
            else:
                # ファイルから認証情報を取得（ローカル実行用）
                creds_file = 'credentials.json'
                if not os.path.exists(creds_file):
                    logger.error(f"認証情報ファイル {creds_file} が見つかりません")
                    return
                creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
                logger.info(f"ファイル {creds_file} から認証情報を取得しました")
            
            # gspreadクライアントを作成
            self.google_sheets_client = gspread.authorize(creds)
            logger.info("Google Sheets APIに接続しました")
        except Exception as e:
            logger.error(f"Google Sheets API接続エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.google_sheets_client = None
    
    def make_scrapingbee_request(self, url, params=None):
        """
        ScrapingBee APIを使用してWebページを取得
        
        Args:
            url: スクレイピング対象のURL
            params: ScrapingBee APIリクエストの追加パラメータ
        
        Returns:
            BeautifulSoupオブジェクト（成功した場合）、またはNone（失敗した場合）
        """
        default_params = {
            'api_key': self.api_key,
            'url': url,
            'render_js': 'true',  # JavaScriptレンダリングを有効化
            'premium_proxy': 'true',  # プレミアムプロキシを使用（ブロック回避）
            'country_code': 'th',  # タイのIPを使用
        }
        
        # パラメータをマージ
        if params:
            default_params.update(params)
        
        try:
            logger.info(f"ScrapingBeeリクエスト: {url}")
            response = requests.get(
                'https://app.scrapingbee.com/api/v1/', 
                params=default_params,
                timeout=60
            )
            
            if response.status_code == 200:
                logger.info(f"ステータス: 200 OK ({len(response.text)} バイト)")
                return BeautifulSoup(response.text, 'html.parser')
            else:
                logger.error(f"ScrapingBeeリクエストエラー: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"ScrapingBeeリクエスト例外: {e}")
            return None
    
    def get_total_pages(self):
        """
        総ページ数を取得
        
        Returns:
            総ページ数（整数）、取得失敗時は1
        """
        soup = self.make_scrapingbee_request(self.base_url)
        if not soup:
            return 1
        
        try:
            # ページネーションの検索
            pagination = soup.select('.pagination')
            if pagination:
                # ページ番号を含む要素を検索
                page_items = pagination[0].select('li.page')
                page_numbers = []
                
                for item in page_items:
                    # data-value属性を確認
                    data_value = item.get('data-value')
                    if data_value and data_value.isdigit():
                        page_numbers.append(int(data_value))
                    # テキスト内容を確認
                    elif item.text and item.text.strip().isdigit():
                        page_numbers.append(int(item.text.strip()))
                
                if page_numbers:
                    return max(page_numbers)
            
            # 別の方法でページネーションを検索
            last_page_link = soup.select('a[data-page="last"]')
            if last_page_link:
                href = last_page_link[0].get('href')
                if href:
                    page_match = re.search(r'page=(\d+)', href)
                    if page_match:
                        return int(page_match.group(1))
            
            # ページ数を見つけられない場合
            return 1
        except Exception as e:
            logger.error(f"ページ数取得エラー: {e}")
            return 1
    
    def extract_property_data_from_card(self, card):
        """
        物件カードから基本情報を抽出
        
        Args:
            card: BeautifulSoupの物件カード要素
        
        Returns:
            辞書形式の物件基本情報
        """
        property_data = {
            'title': '不明',
            'price': '不明',
            'address': '不明',
            'description': '',
            'size': '',
            'url': ''
        }
        
        try:
            # 物件URL
            link_elem = card.select_one('a')
            if link_elem and link_elem.get('href'):
                url = link_elem.get('href')
                if not url.startswith('http'):
                    url = 'https://www.hipflat.co.th' + url
                property_data['url'] = url
            
            # タイトル
            title_elem = card.select_one('.snippet-title')
            if title_elem:
                property_data['title'] = title_elem.text.strip()
            
            # 価格
            price_elem = card.select_one('.snippet-price')
            if price_elem:
                property_data['price'] = price_elem.text.strip()
            
            # 住所
            address_elem = card.select_one('.snippet-address')
            if address_elem:
                property_data['address'] = address_elem.text.strip()
            
            # 説明文
            desc_elem = card.select_one('.snippet-description')
            if desc_elem:
                property_data['description'] = desc_elem.text.strip()
            
            # サイズ/面積情報
            # 複数のセレクタを試行
            size_found = False
            size_selectors = [
                '.snippet-summary li:contains("m²")',
                '.snippet-summary li:nth-child(3)',
                '.snippet-summary li img[src*="space.svg"] + text'
            ]
            
            for selector in size_selectors:
                size_elem = card.select(selector)
                if size_elem:
                    size_text = size_elem[0].text.strip()
                    size_match = re.search(r'(\d+(?:\.\d+)?)\s*m²', size_text)
                    if size_match:
                        property_data['size'] = size_match.group(1) + " m²"
                        size_found = True
                        break
            
            # 上記のセレクタでも取得できない場合はHTMLを直接探索
            if not size_found:
                card_html = str(card)
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*m²', card_html)
                if size_match:
                    property_data['size'] = size_match.group(0)
        
        except Exception as e:
            logger.error(f"物件カード解析エラー: {e}")
        
        return property_data
    
    def get_property_links(self, max_pages=2, start_page=1):
        """
        物件一覧ページから物件リンクと基本情報を収集
        
        Args:
            max_pages: スクレイピングするページ数の上限
            start_page: スクレイピングを開始するページ番号
        
        Returns:
            物件基本情報のリスト（各項目はURL含む辞書）
        """
        total_pages = self.get_total_pages()
        end_page = min(total_pages, max_pages)
        logger.info(f"合計ページ数: {total_pages}, スクレイピング予定: {end_page}ページ")
        
        all_property_data = []
        
        for page_num in range(start_page, end_page + 1):
            page_url = self.base_url if page_num == 1 else f"{self.base_url}?page={page_num}"
            logger.info(f"ページ {page_num}/{end_page} にアクセス: {page_url}")
            
            # ランダムな待機時間を設定（連続リクエストを避けるため）
            if page_num > start_page:
                wait_time = random.uniform(3, 7)
                logger.info(f"{wait_time:.1f}秒待機中...")
                time.sleep(wait_time)
            
            # ページデータを取得
            soup = self.make_scrapingbee_request(page_url)
            if not soup:
                logger.error(f"ページ {page_num} の取得に失敗しました")
                continue
            
            # 物件カードを検索
            property_cards = soup.select('.snippet')
            logger.info(f"検出された物件カード数: {len(property_cards)}")
            
            for card in property_cards:
                property_data = self.extract_property_data_from_card(card)
                if property_data['url']:  # URLがある場合のみ追加
                    all_property_data.append(property_data)
            
            logger.info(f"現在の物件データ数: {len(all_property_data)}")
        
        logger.info(f"全{len(all_property_data)}件の物件基本情報を収集しました")
        return all_property_data
    
    def extract_detail_data(self, soup, basic_info):
        """
        詳細ページから物件詳細情報を抽出
        
        Args:
            soup: 詳細ページのBeautifulSoupオブジェクト
            basic_info: 基本情報を含む辞書
        
        Returns:
            詳細情報を含む辞書
        """
        property_data = {
            '物件名': basic_info.get('title', '不明'),
            '住所': basic_info.get('address', '不明'),
            '1ヶ月賃料': basic_info.get('price', '不明'),
            '物件ID': "不明",
            '最低利用期間': "",
            '建築日付': "",  # 掲載日で上書きされる
            '家具': "",
            'サイズ': basic_info.get('size', ""),
            'サウナ': "なし",
            '階数': "",
            'WiFi': "なし",
            '掲載URL': basic_info.get('url', ""),
            'Line': "",
            'ステータス': ""
        }
        
        try:
            # 物件ID - URLから抽出またはページから取得
            url = basic_info.get('url', '')
            property_id_match = re.search(r'/([^/]+)$', url)
            if property_id_match:
                property_data['物件ID'] = property_id_match.group(1)
            
            # 物件IDをページからも取得を試みる
            id_selectors = [
                '.id .id__text + span',
                '.breadcrumb-custom-item:last-child',
                '.property-id'
            ]
            for selector in id_selectors:
                id_elem = soup.select(selector)
                if id_elem:
                    property_data['物件ID'] = id_elem[0].text.strip()
                    break
            
            # 掲載日情報を取得
            listing_date_selectors = [
                '#basic-information > ul > li:nth-child(1) > span.basic-information__list__item__value',
                '.basic-information__list__item:contains("リストアップされた日付") .basic-information__list__item__value',
                '.basic-information__list__item:contains("掲載日") .basic-information__list__item__value'
            ]
            
            for selector in listing_date_selectors:
                date_elem = soup.select(selector)
                if date_elem:
                    date_text = date_elem[0].text.strip()
                    if date_text:
                        property_data['建築日付'] = date_text
                        break
            
            # HTMLテキスト全体から掲載日を探す
            if not property_data['建築日付']:
                html_text = str(soup)
                date_patterns = [
                    r'リストアップされた日付[：:]\s*([^\<]+)',
                    r'掲載日[：:]\s*([^\<]+)',
                    r'掲載[：:]\s*([^\<]+)'
                ]
                for pattern in date_patterns:
                    match = re.search(pattern, html_text)
                    if match:
                        property_data['建築日付'] = match.group(1).strip()
                        break
            
            # 階数情報を取得
            floor_selectors = [
                'body > main > div.main-header > section.characteristics > div.floor',
                '#basic-information > ul > li:nth-child(4)',
                '.floor .data',
                '.characteristics .floor',
                '.basic-information__list__item:contains("階") .basic-information__list__item__value'
            ]
            
            for selector in floor_selectors:
                floor_elem = soup.select(selector)
                if floor_elem:
                    floor_text = floor_elem[0].text.strip()
                    floor_match = re.search(r'\d+', floor_text)
                    if floor_match:
                        property_data['階数'] = floor_match.group(0)
                    else:
                        property_data['階数'] = floor_text
                    break
            
            # セレクタで取得できない場合はHTMLから検索
            if not property_data['階数']:
                html_text = str(soup)
                floor_patterns = [
                    r'<span class="data">(\d+)</span>\s*<span class="text">階</span>',
                    r'階数[：:]\s*(\d+)',
                    r'(\d+)\s*階'
                ]
                for pattern in floor_patterns:
                    match = re.search(pattern, html_text)
                    if match:
                        property_data['階数'] = match.group(1)
                        break
            
            # 詳細情報セクション
            detail_selectors = [
                '.property-facts',
                '.basic-information__list',
                '.characteristics',
                '.detail-list'
            ]
            
            for selector in detail_selectors:
                details_section = soup.select(selector)
                if details_section:
                    if 'property-facts' in selector:
                        items = details_section[0].select('.fact-item')
                    elif 'basic-information__list' in selector:
                        items = details_section[0].select('.basic-information__list__item')
                    else:
                        items = details_section[0].select('li, .item, .detail-item')
                    
                    for item in items:
                        try:
                            label = None
                            value = None
                            
                            if 'property-facts' in selector:
                                label_elem = item.select_one('.fact-label')
                                value_elem = item.select_one('.fact-value')
                                if label_elem and value_elem:
                                    label = label_elem.text.strip()
                                    value = value_elem.text.strip()
                            elif 'basic-information__list' in selector:
                                label_elem = item.select_one('.basic-information__list__item__label')
                                value_elem = item.select_one('.basic-information__list__item__value')
                                if label_elem and value_elem:
                                    label = label_elem.text.strip()
                                    value = value_elem.text.strip()
                            else:
                                item_text = item.text.strip()
                                if ':' in item_text:
                                    text_parts = item_text.split(':', 1)
                                    label = text_parts[0].strip()
                                    value = text_parts[1].strip()
                            
                            if label and value:
                                if '最低' in label and ('利用' in label or '契約' in label):
                                    property_data['最低利用期間'] = value
                                elif '家具' in label:
                                    property_data['家具'] = value if value else "あり" if "家具" in label else ""
                                elif 'サイズ' in label or '面積' in label or 'エリア' in label:
                                    property_data['サイズ'] = value
                        except Exception as e:
                            logger.error(f"詳細項目の解析エラー: {e}")
                    
                    break  # 詳細セクションが見つかったらループを抜ける
            
            # 物件説明文から追加情報を抽出
            description = basic_info.get('description', "")
            description_selectors = [
                '.description__listing',
                '.description__listing-truncated',
                '.property-description',
                '.detail-description'
            ]
            for selector in description_selectors:
                desc_elem = soup.select(selector)
                if desc_elem:
                    description = desc_elem[0].text.strip()
                    break
            
            # 説明文から追加情報を抽出
            if description:
                # 家具の有無を説明文から判断
                if not property_data['家具'] and ('furnished' in description.lower() or '家具' in description):
                    property_data['家具'] = "あり"
                
                # 最低利用期間を説明文から抽出
                if not property_data['最低利用期間']:
                    contract_patterns = [
                        r'(\d+)\s*(year|年間|ヶ月|か月|カ月)\s*contract',
                        r'contract\s*(\d+)\s*(year|年間|ヶ月|か月|カ月)',
                        r'最低契約期間\s*(\d+)\s*(ヶ月|年間|か月|カ月)',
                        r'契約期間\s*(\d+)\s*(ヶ月|年間|か月|カ月)'
                    ]
                    for pattern in contract_patterns:
                        match = re.search(pattern, description, re.IGNORECASE)
                        if match:
                            property_data['最低利用期間'] = match.group(0)
                            break
            
            # アメニティ情報を取得
            amenity_selectors = [
                '.amenities', 
                '.features__list',
                '.property-features'
            ]
            amenities_found = False
            
            for selector in amenity_selectors:
                amenities_section = soup.select(selector)
                if amenities_section:
                    amenities_found = True
                    
                    if 'amenities' in selector:
                        amenities = amenities_section[0].select('.amenity-item')
                    elif 'features__list' in selector:
                        amenities = amenities_section[0].select('.features__list__item__name')
                    else:
                        amenities = amenities_section[0].select('li, .item')
                    
                    has_sauna = False
                    has_wifi = False
                    
                    for amenity in amenities:
                        amenity_text = amenity.text.strip().lower()
                        
                        if 'sauna' in amenity_text or 'サウナ' in amenity_text:
                            has_sauna = True
                        if any(term in amenity_text for term in ['wifi', 'wi-fi', 'インターネット', 'ネット接続', 'internet']):
                            has_wifi = True
                    
                    property_data['サウナ'] = "あり" if has_sauna else "なし"
                    property_data['WiFi'] = "あり" if has_wifi else "なし"
                    break
            
            # アメニティセクションが見つからなかった場合は説明文から判断
            if not amenities_found and description:
                # WiFi情報を説明文から抽出
                wifi_terms = ['wifi', 'wi-fi', 'インターネット', 'ネット接続', 'internet']
                if any(term in description.lower() for term in wifi_terms):
                    property_data['WiFi'] = "あり"
                
                # サウナ情報を説明文から抽出
                if 'sauna' in description.lower() or 'サウナ' in description:
                    property_data['サウナ'] = "あり"
            
            # Lineやその他連絡先情報
            contact_selectors = [
                '.contact-section',
                '.agent-info',
                '.listing-contact'
            ]
            for selector in contact_selectors:
                contact_section = soup.select(selector)
                if contact_section:
                    contact_text = contact_section[0].text
                    line_match = re.search(r'Line[:\s]*([^\s,]+)', contact_text, re.IGNORECASE)
                    if line_match:
                        property_data['Line'] = line_match.group(1)
                    break
            
            # ステータスを「詳細取得済」に設定
            property_data['ステータス'] = "詳細取得済"
            
        except Exception as e:
            logger.error(f"詳細情報の抽出エラー: {e}")
            property_data['ステータス'] = "エラー"
        
        return property_data
    
    def get_property_details(self, property_list, max_details=5):
        """
        物件詳細情報を取得
        
        Args:
            property_list: 基本情報を含む物件リスト
            max_details: 詳細を取得する物件の最大数
        
        Returns:
            詳細情報を含む物件リスト
        """
        all_results = []
        detail_limit = min(max_details, len(property_list)) if max_details > 0 else 0
        
        # すべての物件の基本データを初期化
        for basic_info in property_list:
            # 基本情報を初期化
            property_data = {
                '物件名': basic_info.get('title', '不明'),
                '住所': basic_info.get('address', '不明'),
                '1ヶ月賃料': basic_info.get('price', '不明'),
                '物件ID': "不明",
                '最低利用期間': "",
                '建築日付': "",
                '家具': "",
                'サイズ': basic_info.get('size', ""),
                'サウナ': "なし",
                '階数': "",
                'WiFi': "なし",
                '掲載URL': basic_info.get('url', ""),
                'Line': "",
                'ステータス': "基本情報のみ"
            }
            
            # URLから物件IDを抽出
            url = basic_info.get('url', '')
            property_id_match = re.search(r'/([^/]+)$', url)
            if property_id_match:
                property_data['物件ID'] = property_id_match.group(1)
            
            # 説明文から基本的な情報を抽出
            description = basic_info.get('description', "")
            if description:
                # 家具の有無を説明文から判断
                if 'furnished' in description.lower() or '家具' in description:
                    property_data['家具'] = "あり"
                
                # WiFi情報を説明文から抽出
                wifi_terms = ['wifi', 'wi-fi', 'インターネット', 'ネット接続', 'internet']
                if any(term in description.lower() for term in wifi_terms):
                    property_data['WiFi'] = "あり"
            
            all_results.append(property_data)
        
        # 詳細情報を取得する場合
        if detail_limit > 0:
            logger.info(f"=== {detail_limit}件の物件の詳細情報を取得 ===")
            
            for idx, basic_info in enumerate(property_list[:detail_limit]):
                url = basic_info.get('url', '')
                if not url:
                    continue
                
                logger.info(f"物件詳細ページにアクセス ({idx+1}/{detail_limit}): {url}")
                
                # リクエスト間の待機時間
                if idx > 0:
                    wait_time = random.uniform(3, 5)
                    logger.info(f"{wait_time:.1f}秒待機中...")
                    time.sleep(wait_time)
                
                # 詳細ページ取得
                soup = self.make_scrapingbee_request(url)
                if not soup:
                    logger.error(f"詳細ページの取得に失敗しました: {url}")
                    continue
                
                # 詳細情報抽出
                detailed_info = self.extract_detail_data(soup, basic_info)
                
                # 対応する基本情報エントリを詳細情報で更新
                all_results[idx] = detailed_info
        
        return all_results
    
    def format_for_spreadsheet(self, df):
        """
        スクレイピング結果の DataFrame を Google Sheets 用に整形する
        """
        required_columns = [
            '物件名', '住所', '1ヶ月賃料', '最低利用期間', '建築日付', 
            '家具', 'サイズ', 'サウナ', '階数', 'WiFi', '掲載URL', 'Line', 'ステータス'
        ]
        
        # 存在しない列は空文字列で追加
        for col in required_columns:
            if col not in df.columns:
                df[col] = ''
        
        formatted_df = df[required_columns].copy()
        formatted_df.insert(0, 'No', range(1, len(formatted_df) + 1))
        
        # WiFi が「あり」の場合のみチェックマークを付与
        formatted_df['WiFi'] = formatted_df['WiFi'].apply(lambda x: '◯' if x == 'あり' else '')
        formatted_df['サウナ'] = formatted_df['サウナ'].apply(lambda x: '◯' if x == 'あり' else '')
        
        return formatted_df
    
    def update_google_sheet(self, df):
        """
        Google Sheetsにデータを書き込む
        
        Args:
            df: 出力するデータフレーム
        
        Returns:
            成功した場合はTrue、失敗した場合はFalse
        """
        if not self.google_sheets_client or not self.spreadsheet_id:
            logger.error("Google Sheetsクライアントが初期化されていないか、スプレッドシートIDが未設定です")
            return False
        
        try:
            # スプレッドシートを開く
            spreadsheet = self.google_sheets_client.open_by_key(self.spreadsheet_id)
            
            # シートを取得または作成
            try:
                worksheet = spreadsheet.worksheet("物件データ")
                # 既存のデータをクリア
                worksheet.clear()
            except gspread.exceptions.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet("物件データ", rows=1000, cols=20)
            
            # 列名を準備
            header = ['No', '物件名', '住所', '1ヶ月賃料', '最低利用期間', '建築日付', 
                     '家具', 'サイズ', 'サウナ', '階数', 'WiFi', '掲載URL', 'Line', 'ステータス']
            
            # データを二次元配列に変換
            values = [header]
            for _, row in df.iterrows():
                values.append([row[col] if col in row else '' for col in header])
            
            # スプレッドシートに書き込み
            worksheet.update(values)
            
            # 書式を設定
            worksheet.format('A1:N1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            
            # URLをハイパーリンクに変換
            for idx, row in df.iterrows():
                if 'URL' in row and row['掲載URL']:
                    cell = f'L{idx + 2}'  # header + 1-based index
                    worksheet.update_cell(idx + 2, 12, row['掲載URL'])
                    worksheet.format(cell, {
                        'textFormat': {'foregroundColor': {'red': 0.0, 'green': 0.0, 'blue': 0.8}},
                        'textFormat': {'underline': True}
                    })
            
            logger.info(f"Google Sheetsへのデータ更新が完了しました。行数: {len(values)}")
            return True
            
        except Exception as e:
            logger.error(f"Google Sheets更新エラー: {e}")
            return False
    
    def scrape_hipflat_apartments(self, max_details=5, max_pages=2, start_page=1, save_csv=False):
        """
        Hipflatサイトからパタヤの賃貸物件情報をスクレイピングする関数
        
        Args:
            max_details: 詳細情報を取得する物件の最大数 (0の場合は基本情報のみ)
            max_pages: スクレイピングするページの最大数
            start_page: スクレイピングを開始するページ番号
            save_csv: CSVファイルに結果を保存するかどうか
            
        Returns:
            pandas.DataFrame: スクレイピング結果のデータフレーム
        """
        logger.info(f"=== Hipflatスクレイピング開始: 最大{max_pages}ページ, 詳細{max_details}件 ===")
        
        # 物件一覧と基本情報を取得
        property_basic_info = self.get_property_links(max_pages=max_pages, start_page=start_page)
        if not property_basic_info:
            logger.error("物件基本情報の取得に失敗しました")
            return None
        
        # 詳細情報を取得
        property_details = self.get_property_details(property_basic_info, max_details=max_details)
        
        logger.info(f"スクレイピングが完了しました。全{len(property_details)}件の物件情報を取得")
        
        # DataFrame に変換
        df = pd.DataFrame(property_details)
        
        # CSVファイルに保存
        if save_csv:
            filename = f'hipflat_pattaya_apartments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            logger.info(f"結果をCSVに保存: {filename}")
        
        # Google Sheets用にフォーマット
        formatted_df = self.format_for_spreadsheet(df)
        
        # Google Sheetsに更新
        if self.spreadsheet_id:
            self.update_google_sheet(formatted_df)
        
        return formatted_df


def main():
    """
    メイン実行関数
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Hipflatパタヤ賃貸物件スクレイピング')
    parser.add_argument('--api-key', help='ScrapingBee APIキー (未指定時は環境変数から取得)')
    parser.add_argument('--spreadsheet-id', help='Google SpreadsheetのID (未指定時は環境変数から取得)')
    parser.add_argument('--max-pages', type=int, default=int(os.environ.get('MAX_PAGES', '2')), 
                        help='スクレイピングする最大ページ数')
    parser.add_argument('--max-details', type=int, default=int(os.environ.get('MAX_DETAILS', '5')), 
                        help='詳細情報を取得する物件の最大数 (0=詳細なし)')
    parser.add_argument('--start-page', type=int, default=int(os.environ.get('START_PAGE', '1')), 
                        help='開始ページ番号')
    parser.add_argument('--save-csv', action='store_true', help='結果をCSVに保存する')
    
    args = parser.parse_args()
    
    # スクレイパーの初期化
    scraper = HipflatScraper(
        args.api_key,
        spreadsheet_id=args.spreadsheet_id
    )
    
    # スクレイピング実行
    df = scraper.scrape_hipflat_apartments(
        max_details=args.max_details,
        max_pages=args.max_pages,
        start_page=args.start_page,
        save_csv=args.save_csv
    )
    
    if df is not None:
        print(f"スクレイピング完了: {len(df)}件の物件情報を取得しました")
    else:
        print("スクレイピングに失敗しました")

if __name__ == "__main__":
    main()