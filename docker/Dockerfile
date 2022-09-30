FROM jxxghp/nas-tools-base-image
ENV LANG="C.UTF-8" \
    TZ="Asia/Taipei" \
    NASTOOL_CONFIG="/config/config.yaml" \
    NASTOOL_AUTO_UPDATE=true \
    PS1="\u@\h:\w \$ " \
    REPO_URL="https://github.com/kindomLee/nas-tools.git" \
    PUID=0 \
    PGID=0 \
    UMASK=000 \
    WORKDIR="/nas-tools" \
    MK_TAG="20220811-1"
WORKDIR ${WORKDIR}
RUN python_ver=$(python3 -V | awk '{print $2}') \
    && echo "${WORKDIR}/" > /usr/lib/python${python_ver%.*}/site-packages/nas-tools.pth \
    && echo 'fs.inotify.max_user_watches=524288' >> /etc/sysctl.conf \
    && echo 'fs.inotify.max_user_instances=524288' >> /etc/sysctl.conf \
    && git config --global pull.ff only \
    && git clone -b master ${REPO_URL} ${WORKDIR} --recurse-submodule \
    && git config --global --add safe.directory ${WORKDIR}
EXPOSE 3000
VOLUME ["/config"]
ENTRYPOINT ["/nas-tools/docker/entrypoint.sh"]