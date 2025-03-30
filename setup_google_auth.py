"""
Google API認証情報のセットアップスクリプト

使用方法:
1. Google Cloud Consoleからサービスアカウントの認証情報JSONをダウンロード
2. このスクリプトを実行し、JSONファイルのパスを指定
3. スプレッドシートIDを入力し、アクセステスト
"""

import os
import json
import argparse
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def setup_auth(credentials_file, test_spreadsheet_id=None):
    """
    Google API認証情報をセットアップし、必要に応じてテスト
    
    Args:
        credentials_file: サービスアカウント認証情報JSONファイルのパス
        test_spreadsheet_id: テスト用スプレッドシートID (任意)
    """
    try:
        # 認証情報ファイルが存在するか確認
        if not os.path.exists(credentials_file):
            print(f"エラー: 認証情報ファイル '{credentials_file}' が見つかりません。")
            return False
        
        # JSONファイルの内容を確認
        with open(credentials_file, 'r') as f:
            creds_data = json.load(f)
        
        required_keys = ['client_email', 'private_key', 'project_id']
        for key in required_keys:
            if key not in creds_data:
                print(f"エラー: 認証情報ファイルに必要なキー '{key}' が含まれていません。")
                return False
        
        print(f"認証情報の確認: OK")
        print(f"- プロジェクト ID: {creds_data['project_id']}")
        print(f"- クライアントメール: {creds_data['client_email']}")
        
        # プロジェクトのルートに認証情報をコピー
        target_path = 'credentials.json'
        if credentials_file != target_path:
            with open(target_path, 'w') as f:
                json.dump(creds_data, f)
            print(f"認証情報を '{target_path}' にコピーしました。")
        
        # APIスコープを設定
        scope = ['https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive']
        
        # 認証情報を使用してgspreadクライアントを作成
        creds = ServiceAccountCredentials.from_json_keyfile_name(target_path, scope)
        client = gspread.authorize(creds)
        
        print(f"Google API認証: 成功")
        
        # スプレッドシートへのアクセスをテスト
        if test_spreadsheet_id:
            try:
                spreadsheet = client.open_by_key(test_spreadsheet_id)
                print(f"スプレッドシート '{spreadsheet.title}' へのアクセス: 成功")
                
                # シート一覧を表示
                print(f"シート一覧:")
                for worksheet in spreadsheet.worksheets():
                    print(f"- {worksheet.title}")
                
                # スプレッドシートにアクセスできることを確認するためにテストデータを書き込み
                print(f"テストデータの書き込みテスト...")
                
                # シートの取得または作成
                try:
                    worksheet = spreadsheet.worksheet("テスト")
                except gspread.exceptions.WorksheetNotFound:
                    worksheet = spreadsheet.add_worksheet("テスト", rows=10, cols=5)
                
                # テストデータを書き込む
                test_data = [
                    ["Hipflatスクレイパー", "テスト"],
                    [f"認証テスト成功", "OK"]
                ]
                worksheet.update(test_data)
                print(f"テストデータの書き込み: 成功")
                
            except Exception as e:
                print(f"スプレッドシートへのアクセスエラー: {e}")
                print("注意: スプレッドシートのアクセス権限を確認してください。")
                print(f"サービスアカウントのメールアドレス '{creds_data['client_email']}' にスプレッドシートの閲覧・編集権限を付与してください。")
                return False
        
        print("\n認証設定が完了しました。")
        if not test_spreadsheet_id:
            print("注意: スプレッドシートをテストしていません。スクレイピング時にアクセス権限エラーが発生する可能性があります。")
            print(f"サービスアカウントのメールアドレス '{creds_data['client_email']}' に対象スプレッドシートの閲覧・編集権限を付与してください。")
        
        return True
        
    except Exception as e:
        print(f"設定エラー: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Google API認証情報のセットアップ')
    parser.add_argument('--credentials', '-c', required=True, help='サービスアカウント認証情報JSONファイルのパス')
    parser.add_argument('--spreadsheet', '-s', help='テスト用スプレッドシートID (任意)')
    
    args = parser.parse_args()
    
    print("=== Google API認証情報のセットアップ ===")
    setup_auth(args.credentials, args.spreadsheet)

if __name__ == "__main__":
    main()