# YANS2022ハッカソン　リーダーボード
## 起動方法（ローカル）
* ./data ディレクトリ以下に leader_board.jsonl ファイルを設置  
* (任意) 固定のセッション暗号化キーを使用したい場合はルート直下に local_settings.py を作成し、以下のようにキーを設定する
  ```python
  SECRET_KEY = "<任意のキー>"
  ```
* 以下を実行して `0.0.0.0:8001` にアクセス
  ```shell
  $ pip3 install -r requirements.txt
  $ python3 app.py
  ```

## 管理者ユーザの作成 on CLI
```shell
$ python3 create_admin.py

ログインIDを入力してください：<ログインID>
パスワードを入力してください：<パスワード>
```

## ユーザ追加 on UI
1. 管理者ユーザでログイン後に左上の「管理画面」をクリックして管理画面に飛ぶ  
2. 管理画面上部のメニューの「User」をクリックしてユーザ管理画面に飛ぶ
3. 「Create」タブを選択
4. 「User Id」にログイン ID、「Print Name」にリーダーボード上での表示名、「Password」にログインパスワードを入力して「Save」をクリック（※その他の入力欄は空欄）

