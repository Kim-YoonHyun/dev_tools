docker run --rm \
    --network host \
	-v /home/gj_anly/ipconfig_cryp.ini:/ipconfig_cryp.ini:ro \
	-v /home/gj_anly/cryptogram:/cryptogram:ro \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/timezone:/etc/timezone:ro \
	test:dev