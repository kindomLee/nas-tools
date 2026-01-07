![logo-blue](https://user-images.githubusercontent.com/51039935/197520391-f35db354-6071-4c12-86ea-fc450f04bc85.png)
# NAS媒體庫資源歸集、整理自動化工具

[![GitHub stars](https://img.shields.io/github/stars/kindomLee/nas-tools?style=plastic)](https://github.com/kindomLee/nas-tools/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/kindomLee/nas-tools?style=plastic)](https://github.com/kindomLee/nas-tools/network/members)
[![GitHub issues](https://img.shields.io/github/issues/kindomLee/nas-tools?style=plastic)](https://github.com/kindomLee/nas-tools/issues)
[![GitHub license](https://img.shields.io/github/license/kindomLee/nas-tools?style=plastic)](https://github.com/kindomLee/nas-tools/blob/master/LICENSE.md)

Docker：https://hub.docker.com/repository/docker/jxxghp/nas-tools

TG頻道：https://t.me/nastool

WIKI：https://github.com/kindomLee/nas-tools/wiki

API: http://localhost:3000/api/v1/


## 功能：

本軟體的初衷是實現影視資源的自動化管理，釋放雙手、聚焦觀影。需要有良好的網路環境及私有站點才能獲得較好的使用體驗。

### 1、資源檢索和訂閱
* 站點RSS聚合，想看的加入訂閱，資源自動即時追新。
* 透過微信、Telegram、Slack或者WEB介面聚合資源搜尋下載，最新熱門資源一鍵搜尋或者訂閱。
* 與豆瓣聯動，在豆瓣中標記想看後臺自動檢索下載，未出全的自動加入訂閱。

### 2、媒體庫整理
* 監控下載軟體，下載完成後自動識別真實名稱，硬連結到媒體庫並重新命名。
* 對目錄進行監控，檔案變化時自動識別媒體資訊硬連結到媒體庫並重新命名。
* 解決保種與媒體庫整理衝突的問題，專為中文環境最佳化，支援國產劇集和動漫，重新命名準確率高，改名後Emby/Jellyfin/Plex 100%搜刮。

### 3、站點養護
* 全面的站點資料統計，即時監測你的站點流量情況。
* 全自動化託管養站，支援遠端下載器。
* 站點每日自動登入保號。

### 4、訊息服務
* 支援ServerChan、微信、Slack、Telegram、Bark、PushPlus、愛語飛飛等圖文訊息通知
* 支援透過微信、Telegram、Slack遠端控制訂閱和下載。
* Emby/Jellyfin/Plex播放狀態通知。


## 安裝
### 1、Docker
```
docker pull jxxghp/nas-tools:latest
```
教學見 [這裡](docker/readme.md) ，如無法連線Github，注意不要開啟自動更新開關(NASTOOL_AUTO_UPDATE=false)。

### 2、本地執行
python3版本，如發現缺少相依套件需額外安裝
```
git clone -b master https://github.com/kindomLee/nas-tools --recurse-submodule
python3 -m pip install -r requirements.txt
export NASTOOL_CONFIG="/xxx/config/config.yaml"
nohup python3 run.py &
```

### 3、Windows
下載exe檔案，雙擊執行即可，會自動產生設定檔目錄

https://github.com/kindomLee/nas-tools/releases

### 4、群暉套件
新增礦神群暉SPK套件源直接安裝：

https://spk.imnks.com/

https://spk7.imnks.com/


## 設定
### 1、申請相關API KEY
* 申請TMDB使用者，在 https://www.themoviedb.org/ 申請使用者，得到API KEY。

* 申請訊息通知服務
  1) 微信（推薦）：在 https://work.weixin.qq.com/ 申請企業微信自建應用，獲得企業ID、自建應用secret、agentid

     微信掃描自建應用二維碼可實現在微信中使用訊息服務，無需開啟企業微信
  2) Server醬：或者在 https://sct.ftqq.com/ 申請SendKey
  3) Telegram（推薦）：關注BotFather申請機器人獲取token，關注getuserID拿到chat_id
  4) Bark：安裝Bark客戶端獲得KEY，可以自建Bark伺服器或者使用預設的伺服器
  5) Slack：在 https://api.slack.com/apps 申請應用，詳情參考頻道說明
  6) 其它：仍然會持續增加對通知渠道的支援，API KEY獲取方式類似，不一一說明

### 2、基礎配置
* 檔案轉移模式說明：目前支援六種模式：複製、硬連結、軟連結、移動、RCLONE、MINIO。

  1) 複製模式下載做種和媒體庫是兩份，多佔用儲存（下載盤大小決定能保多少種），好處是媒體庫的盤不用24小時運行可以休眠；

  2) 硬連結模式不用額外增加儲存空間，一份檔案兩份目錄，但需要下載目錄和媒體庫目錄在一個磁碟分區或者儲存空間；軟連結模式就是快捷方式，需要容器內路徑與真實路徑一致才能正常使用；

  3) 移動模式會移動和刪除原檔案及目錄；

  4) RCLONE模式只針對RCLONE網盤使用場景，**注意，使用RCLONE模式需要自行映射rclone配置目錄到容器中**，具體參考設定項小問號說明；

  5) MINIO只針對S3/雲原生場景，**注意，使用MINIO，媒體庫應當設定為/bucket名/類別名**，例如,bucket的名字叫cloud,電影的分類資料夾名叫movie，則媒體庫電影路徑為：/cloud/movie,最好母集用s3fs掛載到/cloud/movie，只讀就行。


* 啟動程式並配置：Docker預設使用3000埠啟動（群暉套件預設3003埠），預設使用者密碼：admin/password（docker需要參考教學提前映射好埠、下載目錄、媒體庫目錄）。登入管理介面後，在設定中根據每個配置項的提示在WEB頁面修改好配置並重新啟動生效（基礎設定中有標紅星的是必須要配置的，如TMDB APIKEY等），每一個配置項後都有小問號，點選會有詳細的配置說明，推薦閱讀。

### 3、設定媒體庫伺服器
支援 Emby（推薦）、Jellyfin、Plex，設定媒體伺服器後可以對本地資源進行判重避免重複下載，同時能標識本地已存在的資源：
* 在Emby/Jellyfin/Plex的Webhook外掛中，設定地址為：http(s)://IP:PORT/emby、jellyfin、plex，用於接收播放通知（可選）
* 將Emby/Jellyfin/Plex的相關資訊配置到「設定-》媒體伺服器」中
* 如果啟用了預設分類，需按如下的目錄結構分別設定好媒體庫；如是自定義分類，請按自己的定義建立好媒體庫目錄，分類定義請參考default-category.yaml分類配置檔案模板。注意，開啟二級分類時，媒體庫需要將目錄設定到二級分類子目錄中（可新增多個子目錄到一個媒體庫，也可以一個子目錄設定一個媒體庫），否則媒體庫管理軟體可能無法正常搜刮識別。
   > 電影
   >> 精選
   >> 華語電影
   >> 外語電影
   >> 動畫電影
   >
   > 電視劇
   >> 國產劇
   >> 歐美劇
   >> 日韓劇
   >> 動漫
   >> 紀錄片
   >> 綜藝
   >> 兒童

### 4、配置下載器及下載目錄
支援qbittorrent（推薦）、transmission、aria2、115網盤等，右上角按鈕設定好下載目錄。

### 5、配置同步目錄
* 目錄同步可以對多個分散的資料夾進行監控，資料夾中有新增媒體檔案時會自動進行識別重新命名，並按配置的轉移方式轉移到媒體庫目錄或指定的目錄中。
* 如將下載軟體的下載目錄也納入目錄同步範圍的，建議關閉下載軟體監控功能，否則會觸發重複處理。

### 5、配置微信/Slack/Telegram遠端控制
配置好微信、Slack或Telegram機器人後，可以直接透過微信/Slack/Telegram機器人傳送名字實現自動檢索下載，以及透過選單控制程式執行。

1) **微信訊息推送及回撥**

  * 配置訊息推送代理

  由於微信官方限制，2022年6月20日後建立的企業微信應用需要有固定的公網IP地址並加入IP白名單後才能接收到訊息，使用有固定公網IP的代理伺服器轉發可解決該問題

    如使用nginx搭建代理服務，需在配置中增加以下代理配置：
    ```
    location /cgi-bin/gettoken {
      proxy_pass https://qyapi.weixin.qq.com;
    }
    location /cgi-bin/message/send {
      proxy_pass https://qyapi.weixin.qq.com;
    }
    ```

    如使用Caddy搭建代理服務，需在配置中增加以下代理配置（`{upstream_hostport}` 部分不是變數，不要改，原封不動複製貼上過去即可）。
    ```
    reverse_proxy https://qyapi.weixin.qq.com {
      header_up Host {upstream_hostport}
    }
    ```
    注意：代理伺服器僅適用於在微信中接收工具推送的訊息，訊息回撥與代理伺服器無關。


  * 配置微信訊息接收服務
  在企業微信自建應用管理頁面-》API接收訊息 開啟訊息接收服務：

    1) 在微信頁面生成Token和EncodingAESKey，並在NASTool設定->訊息通知->微信中填入對應的輸入項並儲存。

    2) **重新啟動NASTool**。

    3) 微信頁面地址URL填寫：http(s)://IP:PORT/wechat，點確定進行認證。


  * 配置微信選單控制
  透過選單遠端控制工具執行，在https://work.weixin.qq.com/wework_admin/frame#apps 應用自定義選單頁面按如下圖所示維護好選單，選單內容為傳送訊息，訊息內容隨意。

   **一級選單及一級選單下的前幾個子選單順序需要一模一樣**，在符合截圖的示例項後可以自己增加別的二級選單項。

   ![image](https://user-images.githubusercontent.com/51039935/170855173-cca62553-4f5d-49dd-a255-e132bc0d8c3e.png)


2) **Telegram Bot機器人**

  * 在NASTool設定中設定好本程式的外網訪問地址，根據實際網路情況決定是否開啟Telegram Webhook開關。

  **注意：WebHook受Telegram限制，程式執行埠需要設定為以下埠之一：443, 80, 88, 8443，且需要有以網認證的Https證書。**

  * 在Telegram BotFather機器人中按下表維護好bot命令選單（要選），選擇選單或輸入命令執行對應服務，輸入其它內容則啟動聚合檢索。

3) **Slack**

  * 詳情參考頻道說明

  **命令與功能對應關係**

   |  命令   | 功能  |
   |  ----  | ----  |
   | /rss  | RSS訂閱 |
   | /ptt  | 下載檔案轉移 |
   | /ptr  | 刪種 |
   | /pts | 站點簽到 |
   | /rst  | 目錄同步 |
   | /db   | 豆瓣想看 |


### 6、配置索引器
配置索引器，以支援搜尋站點資源：
  * 本工具內建索引器目前已支援大部分主流PT站點及部分公開站點，建議啟用內建索引器。
  * 同時支援Jackett/Prowlarr，需額外搭建對應服務並獲取API Key以及地址等資訊，配置到設定->索引器->Jackett/Prowlarr中。

### 7、配置站點
本工具的電影電視劇訂閱、資源搜尋、站點資料統計、刷流、自動簽到等功能均依賴於正確配置站點資訊，需要在「站點管理->站點維護」中維護好站點RSS連結以及Cookie等。

其中站點RSS連結生成時請儘量選擇影視類資源分類，且勾選副標題。

### 8、整理存量媒體資源
如果你的存量資源所在的目錄與你目錄同步中配置的源路徑目的路徑相同，則可以透過WEBUI或微信/Telegram的「目錄同步」按鈕觸發全量同步。

如果不相同則可以按以下說明操作，手工輸入命令整理特定目錄下的媒體資源：

說明：-d 引數為可選，如不輸入則會自動區分電影/電視劇/動漫分別儲存到對應的媒體庫目錄中；-d 引數有輸入時則不管型別，都往-d目錄中轉移。

* Docker版本，宿主機上執行以下命令，nas-tools修改為你的docker名稱，修改源目錄和目的目錄引數。
   ```
   docker exec -it nas-tools sh
   python3 -m pip install -r third_party.txt
   python3 /nas-tools/app/filetransfer.py -m link -s /from/path -d /to/path
   ```
* 群暉套件版本，ssh到後臺執行以下命令，同樣修改配置檔案路徑以及源目錄、目的目錄引數。
   ```
   /var/packages/py3k/target/usr/local/bin/python3 -m pip install -r /var/packages/nastool/target/third_party.txt
   export NASTOOL_CONFIG=/var/packages/nastool/target/config/config.yaml
   /var/packages/py3k/target/usr/local/bin/python3 /var/packages/nastool/target/app/filetransfer.py -m link -s /from/path -d /to/path
   ```
* 本地直接執行的，cd 到程式根目錄，執行以下命令，修改配置檔案、源目錄和目的目錄引數。
   ```
   python3 -m pip install -r third_party.txt
   export NASTOOL_CONFIG=config/config.yaml
   python3 app/filetransfer.py -m link -s /from/path -d /to/path
   ```

## 鳴謝
* 程式UI模板及圖示來源於開源專案<a href="https://github.com/tabler/tabler">tabler</a>，此外專案中還使用到了開源模組：<a href="https://github.com/igorcmoura/anitopy" target="_blank">anitopy</a>、<a href="https://github.com/AnthonyBloomer/tmdbv3api" target="_blank">tmdbv3api</a>、<a href="https://github.com/pkkid/python-plexapi" target="_blank">python-plexapi</a>、<a href="https://github.com/rmartin16/qbittorrent-api">qbittorrent-api</a>、<a href="https://github.com/Trim21/transmission-rpc">transmission-rpc</a>等
* 感謝 <a href="https://github.com/devome" target="_blank">nevinee</a> 完善docker構建
* 感謝 <a href="https://github.com/tbc0309" target="_blank">tbc0309</a> 適配群暉套件
* 感謝 PR 程式碼、完善WIKI、發布教學的所有大佬
