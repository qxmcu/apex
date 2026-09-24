# typed: false
# frozen_string_literal: true

class Apex < Formula
  desc "Adaptive Tournament Multi-Engine Compression Tool & Next-Gen Container"
  homepage "https://qxmcu.github.io/apex/"
  version "1.3.0"
  license "Apache-2.0"

  on_macos do
    url "https://github.com/qxmcu/apex/releases/download/v1.3.0/apex-v1.3.0-darwin-x86_64.tar.gz"
    sha256 "5c930feae2633f4acaa326423ff2c120fd3c73aa53b6599836661e68b3f4b89b"
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/qxmcu/apex/releases/download/v1.3.0/apex-v1.3.0-linux-x86_64.tar.gz"
      sha256 "360f76a52a27299b7083f35bdf4f78a0a406cd43606dd0d9b142a2417e904ffb"
    end
  end

  def install
    bin.install "apex"

    # Generate and install shell completions
    generate_completions_from_executable(bin/"apex", "completions")
  end

  test do
    assert_match "apex 1.3.0", shell_output("#{bin}/apex --version")
  end
end
