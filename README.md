# Hipflat ScrapingBee Scraper

パタヤの賃貸アパート情報を Hipflat からスクレイピングし、Google Sheets に出力するシステムです。

## 機能

- [ScrapingBee](https://www.scrapingbee.com/) APIを使用した効率的なスクレイピング
- JavaScript処理対応（動的コンテンツの抽出）
- IPローテーションによるブロック回避
- Google Sheetsへの自動出力機能
- 物件詳細情報の取得（オプション）
- スクレイピング過程の詳細なログ出力

## 取得情報

以下の情報を各物件について取得します：

- 物件名
- 住所
- 1ヶ月賃料
- 最低利用期間
- 掲載日（建築日付列に格納）
- 家具の有無
- サイズ/面積
- サウナの有無
- 階数
- WiFiの有無
- 掲載URL
- Line ID（ある場合）

## 前提条件

- Python 3.7以上
- ScrapingBee APIキー
- Google Cloud Platform プロジェクトとサービスアカウント（Google Sheets出力を使用する場合）

## インストール方法

1. 必要なパッケージをインストール

```bash
pip install requests beautifulsoup4 pandas gspread oauth2client
```

2. Google Sheets APIを使用する場合は、サービスアカウントの認証情報を設定

   - Google Cloud Consoleでプロジェクト作成
   - Google Sheets APIとGoogle Drive APIを有効化
   - サービスアカウントを作成し、キーをダウンロード
   - ダウンロードしたJSONファイルを`credentials.json`として保存
   - 出力先のGoogle Sheetsにサービスアカウントのメールアドレスを共有設定

## 使用方法

基本的な使い方:

```bash
python hipflat_scrapingbee.py --api-key YOUR_SCRAPINGBEE_API_KEY
```

すべてのオプション:

```bash
python hipflat_scrapingbee.py --api-key YOUR_SCRAPINGBEE_API_KEY \
                             --spreadsheet-id YOUR_GOOGLE_SPREADSHEET_ID \
                             --max-pages 5 \
                             --max-details 10 \
                             --start-page 1 \
                             --save-csv
```

### 引数の説明

- `--api-key`: ScrapingBee APIキー（必須）
- `--spreadsheet-id`: Google SheetsのID（Google Sheets出力を使用する場合）
- `--max-pages`: スクレイピングする最大ページ数（デフォルト: 2）
- `--max-details`: 詳細情報を取得する物件の最大数（デフォルト: 5、0の場合は詳細情報を取得しない）
- `--start-page`: スクレイピングを開始するページ番号（デフォルト: 1）
- `--save-csv`: 結果をCSVファイルにも保存する

## Python APIとしての使用例

スクリプトをモジュールとしてインポートして使用することもできます：

```python
from hipflat_scrapingbee import HipflatScraper

# スクレイパーの初期化
scraper = HipflatScraper(
    api_key="YOUR_SCRAPINGBEE_API_KEY",
    spreadsheet_id="YOUR_GOOGLE_SPREADSHEET_ID"  # 省略可能
)

# スクレイピングの実行
df = scraper.scrape_hipflat_apartments(
    max_details=10,  # 詳細情報を取得する物件数
    max_pages=3,     # スクレイピングするページ数
    start_page=1,    # 開始ページ
    save_csv=True    # CSVにも保存
)

# 結果を表示
print(df)
```

## 注意事項

- ScrapingBeeの使用にはクレジットが消費されます。効率的な使用を心がけてください。
- 一度に大量のリクエストを行うと、ScrapingBeeの制限やHipflatのブロックが発生する可能性があります。
- 商用目的での使用は各サービスの利用規約に従ってください。

## トラブルシューティング

- APIキーエラー: ScrapingBee APIキーが正しいことを確認してください。
- Google Sheets接続エラー: 認証情報ファイルが正しく設定されていることを確認してください。
- スクレイピングエラー: ログを確認し、ウェブサイトの構造が変更されていないか確認してください。

## ライセンス

MIT