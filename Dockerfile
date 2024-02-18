FROM dzhuang/ikuai_behavioral_control-base
MAINTAINER Dong Zhuang <dzhuang.scut@gmail.com>

ARG USERNAME=bc_user

COPY --chown=$USERNAME behavioral_control /opt/behavioral_control/

RUN chmod +x /opt/behavioral_control/start-server.sh

WORKDIR /opt/behavioral_control/
VOLUME /opt/behavioral_control/local_settings
VOLUME /opt/behavioral_control/log
VOLUME /var/log/nginx

EXPOSE 8030

# Start server
STOPSIGNAL SIGTERM

USER $USERNAME

CMD ["/opt/behavioral_control/start-server.sh"]
