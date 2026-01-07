## 特點

- 基於alpine實現，映象體積小；

- 映象層數少；

- 支援 amd64/arm64 架構；

- 重啟即可更新程式，如果依賴有變化，會自動嘗試重新安裝依賴，若依賴自動安裝不成功，會提示更新映象；

- 可以以非root使用者執行任務，降低程式許可權和潛在風險；

- 可以設定檔案掩碼許可權umask。

## 建立

**注意**

- 媒體目錄的設定必須符合 [配置說明](https://github.com/kindomLee/nas-tools#%E9%85%8D%E7%BD%AE) 的要求。

- umask含義詳見：http://www.01happy.com/linux-umask-analyze 。

- 建立後請根據 [配置說明](https://github.com/kindomLee/nas-tools#%E9%85%8D%E7%BD%AE) 及該檔案本身的註釋，修改`config/config.yaml`，修改好後再重啟容器，最後訪問`http://<ip>:<web_port>`。

**docker cli**

```
docker run -d \
    --name nas-tools \
    --hostname nas-tools \
    -p 3000:3000   `# 預設的webui控制埠` \
    -v $(pwd)/config:/config  `# 冒號左邊請修改為你想在主機上儲存配置檔案的路徑` \
    -v /你的媒體目錄:/你想設定的容器內能見到的目錄    `# 媒體目錄，多個目錄需要分別對映進來` \
    -e PUID=0     `# 想切換為哪個使用者來執行程式，該使用者的uid，詳見下方說明` \
    -e PGID=0     `# 想切換為哪個使用者來執行程式，該使用者的gid，詳見下方說明` \
    -e UMASK=000  `# 掩碼許可權，預設000，可以考慮設定為022` \
    -e NASTOOL_AUTO_UPDATE=false `# 如需在啟動容器時自動升級程程式請設定為true` \
    jxxghp/nas-tools
```

如果你訪問github的網路不太好，可以考慮在建立容器時增加設定一個環境變數`-e REPO_URL="https://ghproxy.com/https://github.com/kindomLee/nas-tools.git" \`。

**docker-compose**

新建`docker-compose.yaml`檔案如下，並以命令`docker-compose up -d`啟動。

```
version: "3"
services:
  nas-tools:
    image: jxxghp/nas-tools:latest
    ports:
      - 3000:3000        # 預設的webui控制埠
    volumes:
      - ./config:/config   # 冒號左邊請修改為你想儲存配置的路徑
      - /你的媒體目錄:/你想設定的容器內能見到的目錄   # 媒體目錄，多個目錄需要分別對映進來，需要滿足配置檔案說明中的要求
    environment: 
      - PUID=0    # 想切換為哪個使用者來執行程式，該使用者的uid
      - PGID=0    # 想切換為哪個使用者來執行程式，該使用者的gid
      - UMASK=000 # 掩碼許可權，預設000，可以考慮設定為022
      - NASTOOL_AUTO_UPDATE=false  # 如需在啟動容器時自動升級程程式請設定為true
     #- REPO_URL=https://ghproxy.com/https://github.com/kindomLee/nas-tools.git  # 當你訪問github網路很差時，可以考慮解釋本行註釋
    restart: always
    network_mode: bridge
    hostname: nas-tools
    container_name: nas-tools
```

## 後續如何更新

- 正常情況下，如果設定了`NASTOOL_AUTO_UPDATE=true`，重啟容器即可自動更新nas-tools程式。

- 設定了`NASTOOL_AUTO_UPDATE=true`時，如果啟動時的日誌提醒你 "更新失敗，繼續使用舊的程式來啟動..."，請再重啟一次，如果一直都報此錯誤，請改善你的網路。

- 設定了`NASTOOL_AUTO_UPDATE=true`時，如果啟動時的日誌提醒你 "無法安裝依賴，請更新映象..."，則需要刪除舊容器，刪除舊映象，重新pull映象，再重新建立容器。

## 關於PUID/PGID的說明

- 如在使用諸如emby、jellyfin、plex、qbittorrent、transmission、deluge、jackett、sonarr、radarr等等的docker映象，請保證建立本容器時的PUID/PGID和它們一樣。

- 在docker宿主上，登陸媒體檔案所有者的這個使用者，然後分別輸入`id -u`和`id -g`可獲取到uid和gid，分別設定為PUID和PGID即可。

- `PUID=0` `PGID=0`指root使用者，它擁有最高許可權，若你的媒體檔案的所有者不是root，不建議設定為`PUID=0` `PGID=0`。

## 如果要硬連線如何對映

參考下圖，由imogel@telegram製作。

![如何對映](volume.png)
