#
# Copyright (c) 2015-2021 Canonical, Ltd.
# 
# This file is part of Talisker
# (see http://github.com/canonical-ols/talisker).
# 
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
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
