BASE="sas"
METRICS="${BASE}-metrics"

GRAPHITE_PORT=9080
STATSD_UDP_PORT=8125


case $1 in
    pull)
        docker pull hopsoft/graphite-statsd
        ;;
    create)
        docker create --name ${METRICS} -p ${GRAPHITE_PORT}:80 -p ${STATSD_UDP_PORT}:8125/udp hopsoft/graphite-statsd
        ;;
    start)
        docker start ${METRICS}
        ;;
    stop)
        docker stop ${METRICS}
        ;;
    clean)
        docker rm ${METRICS}
        ;;
esac
