//! Read-only upstream API/connection probe. No pairing, mounting or input.
use idevice::{ReadWrite, core_device::hid::UniversalHidServiceClient, usbmuxd::UsbmuxdConnection};
use serde_json::json;
use std::{collections::HashSet, time::Duration};

#[tokio::main]
async fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    let _hid_type = std::any::type_name::<UniversalHidServiceClient<Box<dyn ReadWrite>>>();
    if args == ["--capabilities"] {
        println!(
            "{}",
            json!({"upstream_revision":"89702099f4d7552f704f93b4526756abda319ceb",
            "license":"MIT", "hid_api_compiled":true, "ax_snapshot_implemented":false,
            "tap_execution_enabled":false, "physical_validation":false})
        );
        return;
    }
    if args != ["--list"] {
        eprintln!("usage: tacto-ios-transport-probe --capabilities | --list");
        std::process::exit(2);
    }
    let discovery = async {
        let mut mux = UsbmuxdConnection::default().await?;
        mux.get_devices().await
    };
    match tokio::time::timeout(Duration::from_secs(5), discovery).await {
        Ok(Ok(devices)) => {
            let unique: HashSet<_> = devices.iter().map(|device| &device.udid).collect();
            println!(
                "{}",
                json!({"device_count":unique.len(), "connection_count":devices.len(), "input_sent":false})
            );
        }
        _ => {
            println!(
                "{}",
                json!({"error":"usbmux_discovery_unavailable", "input_sent":false})
            );
            std::process::exit(1);
        }
    }
}
